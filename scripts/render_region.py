"""Page assets for one region: a 16-bit elevation WebP, a climate-zone texture and a meta.json.

The example pages draw every region the same way (Detuned: stepped relief, linear bathymetry, no contours, no
illumination) from these three files, on the GPU. Heights are packed as height = BASE + (R*256 + G) * STEP,
lossless (see render_demo.encode); BASE is -11,000 m so the deepest trench and the highest peak both fit.

Sources, in order of preference (`--source auto`):
  hires    data/raw/<region>/hires.tif   from scripts/build_hires.py: region CRS, already on the region grid
  current  data/raw/<region>/merged.tif  from scripts/fetch_region.py: lon/lat, warped here to the web cell

Usage: python scripts/render_region.py <region> [--source auto|hires|current] [--cell METRES]
Writes data/out/<region>/demo/{elev.webp, zones.png, meta.json}, and elev_card.webp when the texture is wider than CARD_PX:
the same encoding averaged down for the gallery cards, which are drawn about 900 px wide and should not download 5 to 9 MB each.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import time
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
import fetch_climate
from areas import AREAS
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import reproject

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "regions" / "sources.json").read_text())
BASE, STEP = -11000.0, 0.5
CURRENT_SOURCES = {  # what fetch_region.py merges, by region (see regions.json 'fetch')
    "default": ["cop_glo90", "emodnet_dtm_2024", "etopo_2022_60s"],
    "world": ["etopo_2022_60s"],
}


def encode(z: np.ndarray, method: int = 6) -> bytes:
    """16-bit heights in R (high byte) and G (low byte), lossless WebP (method 6 is smallest, 4 is faster)."""
    v = np.clip(np.round((np.nan_to_num(z, nan=0.0) - BASE) / STEP), 0, 65535).astype("uint32")
    rgb = np.dstack([(v >> 8) & 255, v & 255, np.zeros_like(v)]).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, "WEBP", lossless=True, quality=100, method=method)
    return buf.getvalue()


CARD_PX = 1800  # widest gallery-card texture: a card is drawn at most about 900 CSS px wide, so 2x for a dense screen


def card_texture(z: np.ndarray, cell: float, max_w: int = CARD_PX) -> tuple[np.ndarray, float] | None:
    """The grid averaged k x k (the smallest integer k that brings the width within `max_w`), or None if it is already small enough.

    The grid is padded to a whole number of blocks by repeating its last row and column, so the card covers the same extent as
    the full texture (the last card cell overshoots the edge by less than one card cell); cutting the remainder would shift it."""
    h, w = z.shape
    k = -(-w // max_w)
    if k <= 1:
        return None
    z = np.nan_to_num(z, nan=0.0)  # as encode() does
    ph, pw = -h % k, -w % k
    zp = np.pad(z, ((0, ph), (0, pw)), mode="edge")
    small = zp.reshape(zp.shape[0] // k, k, zp.shape[1] // k, k).mean(axis=(1, 3))
    return small.astype("float32"), cell * k


def decode(blob: bytes) -> np.ndarray:
    """Inverse of encode (used by tests)."""
    a = np.asarray(Image.open(io.BytesIO(blob)).convert("RGB")).astype("uint32")
    return BASE + ((a[..., 0] << 8) | a[..., 1]) * STEP


def load_current(region: str, cell: float) -> tuple[np.ndarray, list[str], str]:
    a = AREAS[region]
    x0, y0, x1, y1 = a["extent"]
    w, h = math.ceil((x1 - x0) / cell), math.ceil((y1 - y0) / cell)
    tr = rasterio.Affine(cell, 0, x0, 0, -cell, y1)
    z = np.full((h, w), np.nan, dtype="float32")
    with rasterio.open(ROOT / "data" / "raw" / region / "merged.tif") as s:
        step_m = s.res[1] * 111_000
        reproject(rasterio.band(s, 1), z, dst_transform=tr, dst_crs=a["crs"], dst_nodata=np.nan, tolerance=0.0,
                  resampling=Resampling.average if cell >= step_m else Resampling.bilinear)
    ids = CURRENT_SOURCES.get(region, CURRENT_SOURCES["default"])
    note = f"merged at {step_m:.0f} m (north-south) by fetch_region.py, shown at {cell:.0f} m"
    return np.nan_to_num(z, nan=0.0), ids, note


def load_hires(region: str) -> tuple[np.ndarray, float, list[str], str]:
    meta = json.loads((ROOT / "data" / "raw" / region / "hires.json").read_text())
    with rasterio.open(ROOT / "data" / "raw" / region / "hires.tif") as s:
        z = np.nan_to_num(s.read(1), nan=0.0)
    ids = meta["land_sources"] + [x for x in meta["sea_sources"] if x not in meta["land_sources"]]
    return z, float(meta["cell_m"]), ids, f"high-resolution build {meta['built']}, finest source {meta['finest_source_m']} m"


def resample(z: np.ndarray, cell: float, to: float, region: str) -> np.ndarray:
    """Average a region grid to a coarser cell on the same top-left origin."""
    x0, _, x1, y1 = AREAS[region]["extent"]
    w, h = math.ceil((x1 - x0) / to), math.ceil((AREAS[region]["extent"][3] - AREAS[region]["extent"][1]) / to)
    out = np.full((h, w), np.nan, dtype="float32")
    reproject(z, out, src_transform=rasterio.Affine(cell, 0, x0, 0, -cell, y1), src_crs=AREAS[region]["crs"],
              dst_transform=rasterio.Affine(to, 0, x0, 0, -to, y1), dst_crs=AREAS[region]["crs"], resampling=Resampling.average)
    return np.nan_to_num(out, nan=0.0)


def zones_texture(region: str, tr, w: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    import render_demo  # climate_zones: Köppen-Geiger classes -> blurred zone weights (cross-blended tints)
    zones = render_demo.climate_zones(fetch_climate.ensure(), tr, w, h, AREAS[region]["crs"])
    q = max(1, min(4, h // 64, w // 64))  # smooth field: quarter size for big grids, full size for tiny ones
    hh, ww = h // q * q, w // q * q
    small = zones[:hh, :ww, :3].reshape(hh // q, q, ww // q, q, 3).mean(axis=(1, 3))
    return zones, np.round(small).astype("uint8")


def main(region: str, source: str = "auto", cell: float | None = None) -> None:
    t0 = time.time()
    raw = ROOT / "data" / "raw" / region
    use = source if source != "auto" else ("hires" if (raw / "hires.tif").exists() else "current")
    plan = PLAN["regions"][region]
    if use == "hires":
        z, cell_m, ids, note = load_hires(region)
        web = cell or plan["web_cell_m"]["hires"]
        if web > cell_m * 1.05:  # the single texture stays web-sized; the tiles (build_tiles.py) carry the fine detail
            z = resample(z, cell_m, web, region)
            note += f"; this single texture is averaged to {web:.0f} m, tiles keep {cell_m:.0f} m"
            cell_m = web
        tr = rasterio.Affine(cell_m, 0, AREAS[region]["extent"][0], 0, -cell_m, AREAS[region]["extent"][3])
    else:
        cell_m = cell or plan["web_cell_m"]["now"]
        z, ids, note = load_current(region, cell_m)
        tr = rasterio.Affine(cell_m, 0, AREAS[region]["extent"][0], 0, -cell_m, AREAS[region]["extent"][3])
    h, w = z.shape
    out = ROOT / "data" / "out" / region / "demo"
    out.mkdir(parents=True, exist_ok=True)
    blob = encode(z)
    (out / "elev.webp").write_bytes(blob)
    card = card_texture(z, cell_m)
    card_blob = encode(card[0]) if card else None
    if card_blob:
        (out / "elev_card.webp").write_bytes(card_blob)
    else:
        (out / "elev_card.webp").unlink(missing_ok=True)  # never leave a card from an earlier, larger build
    zones, small = zones_texture(region, tr, w, h)
    Image.fromarray(small, "RGB").save(out / "zones.png", optimize=True)
    land = z > 0
    names = ["temperate", "boreal", "tundra", "arid"]
    share = {n: round(float((zones[..., i][land] > 127).mean()), 3) if land.any() else 0.0 for i, n in enumerate(names)}
    sources = PLAN["sources"]
    meta = {
        "area": region, "name": AREAS[region]["name"], "crs": AREAS[region]["crs"], "cell": cell_m,
        "bounds": list(AREAS[region]["extent"]), "size": [w, h], "zmin": float(z.min()), "zmax": float(z.max()),
        "encoding": {"base": BASE, "step": STEP, "channels": "R high byte, G low byte"},
        "zones": {"source": "Beck et al. (2023) Köppen-Geiger 1991-2020, 1 km, CC BY 4.0", "share_of_land": share},
        "data": {"kind": use, "note": note, "sources": [{"id": i, "name": sources[i]["name"], "res_m": sources[i]["res_m"]} for i in ids],
                 "attribution": sorted({sources[i]["attribution"].replace("{date}", date.today().isoformat()).replace("{year}", str(date.today().year)) for i in ids})},
        "plan": {"hires_cell_m": plan["web_cell_m"]["hires"], "gain": plan["gain"]},
        "built": date.today().isoformat(),
        "files": {"elev.webp": len(blob), "zones.png": (out / "zones.png").stat().st_size},
    }
    if card:
        meta["card"] = {"file": "elev_card.webp", "size": [card[0].shape[1], card[0].shape[0]], "cell": card[1]}
        meta["files"]["elev_card.webp"] = len(card_blob)
    (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    mb = len(blob) / 1e6
    warn = ""
    if max(w, h) > PLAN["limits"]["texture_px"]:
        warn += f"  WARNING: {max(w, h)} px exceeds the {PLAN['limits']['texture_px']} px texture limit"
    if mb > PLAN["limits"]["web_budget_mb_per_region"]:
        warn += f"  WARNING: {mb:.1f} MB exceeds the {PLAN['limits']['web_budget_mb_per_region']} MB web budget"
    print(f"{region}: {use}, {w} x {h} at {cell_m:.0f} m, elev.webp {mb:.2f} MB"
          + (f", card {card[0].shape[1]} x {card[0].shape[0]} at {card[1]:.0f} m {len(card_blob) / 1e6:.2f} MB" if card else "")
          + f" ({time.time() - t0:.0f} s){warn}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("region")
    ap.add_argument("--source", choices=["auto", "hires", "current"], default="auto")
    ap.add_argument("--cell", type=float)
    a = ap.parse_args()
    main(a.region, a.source, a.cell)
