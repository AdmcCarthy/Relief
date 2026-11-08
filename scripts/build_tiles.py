"""Cut a region's elevation grid into a tile pyramid, so the browser can show 25 to 250 m data when zoomed in.

One 16-bit texture caps a whole-region example at about 8,192 px and 10 MB (regions/sources.json 'limits'). Tiles lift
that: the page fetches only the tiles in view, at the pyramid level that matches the zoom.

Layout (data/out/<region>/tiles/):
  tiles.json            region CRS, extent, tile size, encoding, and per level: cell (m), size (px), grid (tiles)
  <z>/<x>_<y>.webp      512 px tiles, lossless 16-bit height in R (high byte) and G (low byte), as the demo texture
Level z = 0 is the coarsest (the whole region in one tile); the last level is the finest, the grid's own cell. Each
level is a 2 x 2 block mean of the one below it. Tile (x, y) holds pixels x*512 .. x*512 + 511 (y counted from the
north edge of the extent); edge tiles are smaller. Pixel (i, j) of level z covers metres
[x0 + i*cell_z, x0 + (i+1)*cell_z] east and [y1 - (j+1)*cell_z, y1 - j*cell_z] north, in the region CRS.

Usage: python scripts/build_tiles.py <region> [--source auto|hires|current] [--cell METRES]
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from areas import AREAS
from render_region import BASE, STEP, encode, load_current

ROOT = Path(__file__).resolve().parents[1]
TILE = 512


def level_sizes(w: int, h: int, cell: float, tile: int = TILE) -> list[dict]:
    """Pyramid levels, coarsest first: halve until the whole level fits in one tile."""
    levels = [{"cell": cell, "size": [w, h]}]
    while max(w, h) > tile:
        w, h, cell = math.ceil(w / 2), math.ceil(h / 2), cell * 2
        levels.append({"cell": cell, "size": [w, h]})
    levels.reverse()
    for z, lv in enumerate(levels):
        lv["z"] = z
        lv["grid"] = [math.ceil(lv["size"][0] / tile), math.ceil(lv["size"][1] / tile)]
    return levels


def halve(a: np.ndarray) -> np.ndarray:
    """2 x 2 block mean; an odd last row or column is repeated so every output cell has four inputs."""
    if a.shape[0] % 2:
        a = np.vstack([a, a[-1:]])
    if a.shape[1] % 2:
        a = np.hstack([a, a[:, -1:]])
    return a.reshape(a.shape[0] // 2, 2, a.shape[1] // 2, 2).mean(axis=(1, 3)).astype("float32")


def write_level(a: np.ndarray, folder: Path, grid: list[int], tile: int = TILE) -> int:
    folder.mkdir(parents=True, exist_ok=True)

    def one(xy):
        x, y = xy
        blob = encode(a[y * tile:(y + 1) * tile, x * tile:(x + 1) * tile], method=4)
        (folder / f"{x}_{y}.webp").write_bytes(blob)
        return len(blob)

    with ThreadPoolExecutor(4) as ex:
        return sum(ex.map(one, [(x, y) for y in range(grid[1]) for x in range(grid[0])]))


def main(region: str, source: str = "auto", cell: float | None = None) -> None:
    t0 = time.time()
    raw = ROOT / "data" / "raw" / region
    use = source if source != "auto" else ("hires" if (raw / "hires.tif").exists() else "current")
    if use == "hires":
        meta = json.loads((raw / "hires.json").read_text())
        with rasterio.open(raw / "hires.tif") as s:
            z = np.nan_to_num(s.read(1), nan=0.0).astype("float32")
        cell_m, attribution = float(meta["cell_m"]), meta["attribution"]
        built = meta["built"]
    else:
        plan = json.loads((ROOT / "regions" / "sources.json").read_text())["regions"][region]["web_cell_m"]
        cell_m = cell or plan["now"]
        z = load_current(region, cell_m)[0].astype("float32")
        attribution, built = [], date.today().isoformat()
    out = ROOT / "data" / "out" / region / "tiles"
    if out.exists():
        shutil.rmtree(out)
    h, w = z.shape
    levels = level_sizes(w, h, cell_m)
    total = 0
    a = z
    for lv in reversed(levels):  # finest first, halving as we go up
        assert list(a.shape[::-1]) == lv["size"], (a.shape, lv)
        total += write_level(a, out / str(lv["z"]), lv["grid"])
        lv["bytes"] = sum(p.stat().st_size for p in (out / str(lv["z"])).glob("*.webp"))
        a = halve(a)
    doc = {"region": region, "crs": AREAS[region]["crs"], "extent": list(AREAS[region]["extent"]), "tile": TILE,
           "encoding": {"base": BASE, "step": STEP, "channels": "R high byte, G low byte"}, "levels": levels,
           "source": use, "built": built, "attribution": attribution, "total_bytes": total}
    (out / "tiles.json").write_text(json.dumps(doc, indent=1))
    n = sum(lv["grid"][0] * lv["grid"][1] for lv in levels)
    print(f"{region}: {use}, {len(levels)} levels, finest {cell_m:.0f} m ({w} x {h}), {n} tiles, {total / 1e6:.1f} MB ({time.time() - t0:.0f} s)")


def tile_of(doc: dict, z: int, x_m: float, y_m: float) -> tuple[int, int]:
    """The (x, y) of the tile holding a point in region metres at level z (used by tests and the page's logic)."""
    lv = doc["levels"][z]
    x0, _, _, y1 = doc["extent"]
    return int((x_m - x0) / lv["cell"] // doc["tile"]), int((y1 - y_m) / lv["cell"] // doc["tile"])


def load_tile(folder: Path, z: int, x: int, y: int) -> np.ndarray:
    from render_region import decode
    return decode((folder / str(z) / f"{x}_{y}.webp").read_bytes())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("region")
    ap.add_argument("--source", choices=["auto", "hires", "current"], default="auto")
    ap.add_argument("--cell", type=float)
    a = ap.parse_args()
    main(a.region, a.source, a.cell)
