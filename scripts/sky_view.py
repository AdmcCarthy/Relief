"""Sky-view factor: how much of the sky each cell sees, and the `sky` shade model built on it.

A hillshade lights every slope by its own gradient, so a fjord floor and an open plain under the same slope take the same
tone. The sky-view factor (Zaksek, Ostir and Kokalj 2011) adds what the hillshade cannot see: the horizon. A cell in a
trench or at the foot of a wall sees a thin strip of sky and darkens; a plateau or a summit sees the whole dome and lifts.
Used as the ambient term of a shade it gives relief its massing without the harshness of a single low light.

Method, chosen for speed on large print grids in plain numpy:
  - 16 lattice directions (the 8 principal ones and the 8 knight moves), so every sample is a whole-cell shift and no
    cell is interpolated; each direction is weighted by the width of its sector;
  - distances along each direction grow geometrically (1, 2, 3, 4, 6, 8, 11, 16, ...) to the search radius: near
    walls set the horizon exactly, far ridges are sampled at the angular resolution they need. This is the interval
    idea behind radiance cascades (Sannikov 2023) applied to the one problem a terrain has, the horizon;
  - the horizon angle is the running maximum of (height difference / distance), taken on exaggerated heights as
    the hillshade is, so both read the same relief.
Cost is 16 x 12 shift-and-max passes: about 1 s per million cells. Beyond the frame the terrain is unknown and is
treated as open sky.

    python scripts/sky_view.py <region>      bake data/out/<region>/demo/skyview.webp (uint8, 255 = the whole sky)
                                             from the demo texture, recorded under "skyview" in meta.json
"""

from __future__ import annotations

import argparse
import io
import json
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image
from render_region import card_texture

ROOT = Path(__file__).resolve().parents[1]

# (east, north) steps: the principal directions and the knight moves, 16 in all, clockwise from north
DIRECTIONS = [
    (0, 1),
    (1, 2),
    (1, 1),
    (2, 1),
    (1, 0),
    (2, -1),
    (1, -1),
    (1, -2),
    (0, -1),
    (-1, -2),
    (-1, -1),
    (-2, -1),
    (-1, 0),
    (-2, 1),
    (-1, 1),
    (-1, 2),
]
MULTIPLIERS = [1, 2, 3, 4, 6, 8, 11, 16, 23, 32, 45, 64, 91, 128, 181, 256]
AMBIENT = 0.6  # strength of the sky light in the `sky` model: a cell that sees no sky loses this share of its tone


def exaggeration(cell: float) -> float:
    """The house rule shared with the hillshades: 2 x, growing with the cell beyond 1 km so relief does not go flat."""
    return 2.0 * max(1.0, cell / 1000)


def sector_weights() -> np.ndarray:
    """Each direction's share of the compass: half the gap to each neighbour. Sums to 1."""
    az = np.array([math.atan2(e, n) for e, n in DIRECTIONS])
    az = np.mod(az, 2 * math.pi)
    order = np.argsort(az)
    s = az[order]
    gaps = np.diff(np.concatenate([s, [s[0] + 2 * math.pi]]))
    w = np.empty_like(s)
    w[order] = (gaps + np.roll(gaps, 1)) / 2 / (2 * math.pi)
    return w


def search_cells(
    cell: float, radius_m: float = 20_000.0, lo: int = 16, hi: int = 128
) -> int:
    """Search radius in cells: about 20 km, held between 16 and 128 cells."""
    return int(min(hi, max(lo, round(radius_m / cell))))


def horizon_tan(
    zz: np.ndarray, east: int, north: int, cell: float, max_cells: int
) -> np.ndarray:
    """tan of the horizon angle towards (east, north), the running maximum over geometric distances; 0 where open."""
    h, w = zz.shape
    best = np.zeros_like(zz)
    unit = math.hypot(east, north) * cell
    for k in MULTIPLIERS:
        if k * math.hypot(east, north) > max_cells:
            break
        dc, dr = east * k, -north * k  # rows run south
        r0, r1 = max(0, -dr), min(h, h - dr)
        c0, c1 = max(0, -dc), min(w, w - dc)
        if r1 <= r0 or c1 <= c0:
            break
        tgt = (slice(r0, r1), slice(c0, c1))
        src = (slice(r0 + dr, r1 + dr), slice(c0 + dc, c1 + dc))
        np.maximum(best[tgt], (zz[src] - zz[tgt]) / (unit * k), out=best[tgt])
    return best


def sky_view(
    z: np.ndarray, cell: float, exag: float | None = None, max_cells: int | None = None
) -> np.ndarray:
    """Sky-view factor in [0, 1]: 1 on open ground, lower where the horizon rises. Heights exaggerated as the shade is."""
    exag = exaggeration(cell) if exag is None else exag
    max_cells = search_cells(cell) if max_cells is None else max_cells
    zz = (np.nan_to_num(z, nan=0.0) * exag).astype("float32")
    blocked = np.zeros_like(zz)
    for (east, north), w in zip(DIRECTIONS, sector_weights()):
        t = horizon_tan(zz, east, north, cell, max_cells)
        blocked += w * (t / np.sqrt(1.0 + t * t))  # sin of the horizon angle
    return np.clip(1.0 - blocked, 0.0, 1.0)


def sky_hillshade(
    z: np.ndarray,
    cell: float,
    ambient: float = AMBIENT,
    exag: float | None = None,
    max_cells: int | None = None,
    svf: np.ndarray | None = None,
) -> np.ndarray:
    """Shade multiplier (1.0 = flat, open): the soft six-light shade multiplied by the sky light, 1 - ambient * (1 - svf).

    Multiplying keeps the light direction: a lit slope stays lighter than flat ground, a hollow loses up to `ambient`
    of its tone as its sky closes. (Adding the two terms instead lets nothing rise above flat ground, which on gentle
    regional grids darkened every slope and lost the light; tried and dropped 2026-11-15.) Same model as the WebGL
    `sky` mode in preview/relief.js.
    """
    from print_layers import soft_hillshade

    exag = exaggeration(cell) if exag is None else exag
    direct = soft_hillshade(z, cell, exag=exag)
    svf = sky_view(z, cell, exag=exag, max_cells=max_cells) if svf is None else svf
    return direct * (1.0 - ambient * (1.0 - svf))


def bake(region: str) -> dict:
    d = ROOT / "data" / "out" / region / "demo"
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    base, step = meta["encoding"]["base"], meta["encoding"]["step"]
    a = np.asarray(
        Image.open(io.BytesIO((d / "elev.webp").read_bytes())).convert("RGB")
    ).astype("uint32")
    z = (base + ((a[..., 0] << 8) | a[..., 1]) * step).astype("float32")
    cell = float(meta["cell"])
    t0 = time.perf_counter()
    svf = sky_view(z, cell)
    seconds = round(time.perf_counter() - t0, 1)
    # lossy WebP: the factor is smooth, so quality 85 is a tenth of the lossless size and the page cannot tell
    Image.fromarray(np.round(svf * 255).astype("uint8"), "L").save(
        d / "skyview.webp", "WEBP", quality=85, method=6
    )
    meta["skyview"] = {
        "file": "skyview.webp",
        "encoding": "uint8 = sky-view factor x 255 (255 = the whole sky), lossy WebP quality 85",
        "exaggeration": exaggeration(cell),
        "directions": len(DIRECTIONS),
        "search_cells": search_cells(cell),
        "search_km": round(search_cells(cell) * cell / 1000, 1),
        "mean": round(float(svf.mean()), 3),
        "seconds": seconds,
    }
    meta["files"]["skyview.webp"] = (d / "skyview.webp").stat().st_size
    # the gallery draws wide regions from a card-sized texture (meta "card"): give it a factor at the same size
    card = card_texture(svf, cell) if meta.get("card") else None
    if card:
        Image.fromarray(np.round(card[0] * 255).astype("uint8"), "L").save(
            d / "skyview_card.webp", "WEBP", quality=85, method=6
        )
        meta["skyview"]["card"] = "skyview_card.webp"
        meta["files"]["skyview_card.webp"] = (d / "skyview_card.webp").stat().st_size
    else:
        (d / "skyview_card.webp").unlink(missing_ok=True)
    (d / "meta.json").write_text(
        json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return meta["skyview"]


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("region")
    a = p.parse_args()
    info = bake(a.region)
    print(
        f"{a.region}: sky view mean {info['mean']}, {info['directions']} directions to {info['search_km']} km, {info['seconds']} s"
    )


if __name__ == "__main__":
    main()
