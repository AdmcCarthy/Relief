"""Fine base for field-scale maps: a rectangle of a region's merged grid at the grid's own cell, rendered once.

A region's base tint is drawn on its regional grid (900 m for the North Sea frames) and its finest hillshade on the detail
grid (300 m). A consumer that draws many small windows (a 30 km field map is 100 detail pixels) needs the same base at the
merged grid's cell, and may not colour or shade terrain itself. This script cuts a rectangle on whole cells from
data/raw/<region>/hires.tif and writes, for that rectangle:

  elevation.tif              float32 metres (land positive, sea negative), region CRS, deflate
  base_light.png, base_dark.png (+ .webp)   the Detuned tint: linear sea on the region's depth scale, linear land
                             cross-blended by climate zone; the same functions and stops as base_tint.py
  hillshade.png              the sky shade as build.py ships it: flat open ground at 180 of 255
  shade.png (+ .webp)        the same shade with flat ground at mid grey (128) and slopes stretched 2.5 times, as
                             regional_shade.webp: composite with soft-light as it is
  manifest.json              exact extent, cell, size, CRS, depth scale and ticks, land scale, shade model, sources, attribution

The shade is computed on the rectangle padded by the sky-view search radius, then trimmed, so its edges match what a larger
grid would give. Vertical exaggeration is the house rule (2 x at cells up to 1 km); there is no separate setting for flat shelves.

Usage: uv run python scripts/fine_base.py <region> [--extent X0 Y0 X1 Y1] [--name fine]
  --extent  projected metres in the region CRS, on whole cells of the merged grid (default: the region's extent)
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import base_tint as bt
import fetch_climate
import numpy as np
import rasterio
from areas import AREAS
from build import FLAT, HILLSHADE_MODEL, shade_png
from PIL import Image
from sky_view import AMBIENT, exaggeration, search_cells

ROOT = Path(__file__).resolve().parents[1]
ZONE_CELL_M = 1000  # the climate-zone weights are smooth (6 km blend): computed at about 1 km and enlarged
GAIN = 2.5  # slope stretch of the neutral shade, as base_tint.py's regional_shade.webp

Image.MAX_IMAGE_PIXELS = None  # these are our own large rasters


def window_of(extent: list[float], grid_extent: list[float], cell: float) -> tuple[int, int, int, int]:
    """Rows and columns (r0, r1, c0, c1) of `extent` in a grid whose top-left corner is (grid x0, grid y1).

    The rectangle must fall on whole cells and inside the grid: a consumer crops by arithmetic on the extent."""
    x0, y0, x1, y1 = extent
    gx0, gy0, gx1, gy1 = grid_extent
    idx = [(x0 - gx0) / cell, (x1 - gx0) / cell, (gy1 - y1) / cell, (gy1 - y0) / cell]
    if any(abs(v - round(v)) > 1e-6 for v in idx):
        raise ValueError(f"extent {extent} does not fall on whole {cell:g} m cells of the grid {grid_extent}")
    c0, c1, r0, r1 = (round(v) for v in idx)
    if not (0 <= c0 < c1 <= round((gx1 - gx0) / cell) and 0 <= r0 < r1 <= round((gy1 - gy0) / cell)):
        raise ValueError(f"extent {extent} is not inside the grid {grid_extent}")
    return r0, r1, c0, c1


def tints(z: np.ndarray, weights: np.ndarray, bathy: str) -> dict[str, np.ndarray]:
    """The Detuned tint in both themes (uint8 RGB), by base_tint.py's ramps."""
    out = {theme: np.empty(z.shape + (3,), dtype="uint8") for theme in ("light", "dark")}
    for r in range(0, z.shape[0], 512):  # in bands of rows: the ramps work in float32 RGB per zone
        zb, wb = z[r:r + 512], weights[r:r + 512]
        sea = zb < 0
        for theme, img in out.items():
            if bathy == "ocean":
                s = bt.linear_ramp(-zb / bt.OCEAN_MAX, bt.OCEAN_SB, bt.DETUNED_OCEAN[theme], bt.OCEAN_MAX)
            else:
                s = bt.linear_ramp(-zb / bt.SMAX, bt.SB, bt.DETUNED_SEA[theme], bt.SMAX)
            land = bt.linear_land(np.maximum(zb, 0), wb, theme)
            img[r:r + 512] = np.round(np.clip(np.where(sea[..., None], s, land), 0, 255)).astype("uint8")
    return out


def neutral(shade: np.ndarray) -> np.ndarray:
    """The shipped shade (flat at FLAT, 0..1) as uint8 with flat ground at 128 and the slopes stretched GAIN times."""
    return np.round(np.clip(128 + (shade * 255 - FLAT * 255) * GAIN, 0, 255)).astype("uint8")


def zone_weights(region: str, extent: list[float], shape: tuple[int, int]) -> np.ndarray:
    """Climate-zone weights (temperate, boreal, tundra, arid) for the rectangle, enlarged from about 1 km."""
    import render_demo

    x0, y0, x1, y1 = extent
    w, h = max(2, round((x1 - x0) / ZONE_CELL_M)), max(2, round((y1 - y0) / ZONE_CELL_M))
    tr = rasterio.Affine((x1 - x0) / w, 0, x0, 0, -(y1 - y0) / h, y1)
    zones = render_demo.climate_zones(fetch_climate.ensure(), tr, w, h, AREAS[region]["crs"])
    big = np.dstack([np.asarray(Image.fromarray(zones[..., c], "L").resize((shape[1], shape[0]), Image.BILINEAR), dtype=np.float32) for c in range(4)])
    s = big.sum(axis=-1, keepdims=True)
    s[s == 0] = 1
    return big / s


def render(region: str, extent: list[float] | None = None, name: str = "fine") -> dict:
    a = AREAS[region]
    raw = ROOT / "data" / "raw" / region
    prov = json.loads((raw / "hires.json").read_text(encoding="utf-8"))
    sources = json.loads((ROOT / "regions" / "sources.json").read_text(encoding="utf-8"))["sources"]
    extent = [float(v) for v in (extent or a["extent"])]
    with rasterio.open(raw / "hires.tif") as src:
        cell = float(abs(src.res[0]))
        grid_extent = [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]
        r0, r1, c0, c1 = window_of(extent, grid_extent, cell)
        pad = search_cells(cell)
        pr0, pr1, pc0, pc1 = max(0, r0 - pad), min(src.height, r1 + pad), max(0, c0 - pad), min(src.width, c1 + pad)
        zp = np.nan_to_num(src.read(1, window=((pr0, pr1), (pc0, pc1))).astype("float32"), nan=0.0)
        crs = src.crs
    shade = shade_png(zp, cell)[r0 - pr0:r1 - pr0, c0 - pc0:c1 - pc0]
    z = zp[r0 - pr0:r1 - pr0, c0 - pc0:c1 - pc0]
    del zp
    h, w = z.shape
    out = ROOT / "data" / "out" / region / name
    out.mkdir(parents=True, exist_ok=True)
    tr = rasterio.Affine(cell, 0, extent[0], 0, -cell, extent[3])
    with rasterio.open(out / "elevation.tif", "w", driver="GTiff", dtype="float32", count=1, width=w, height=h, crs=crs, transform=tr,
                       compress="deflate", predictor=3, tiled=True) as d:
        d.write(z, 1)
    bathy = a.get("bathymetry", "shelf")
    weights = zone_weights(region, extent, (h, w))
    files = {"elevation": "elevation.tif"}
    for theme, img in tints(z, weights, bathy).items():
        im = Image.fromarray(img, "RGB")
        im.save(out / f"base_{theme}.png", optimize=True)
        im.save(out / f"base_{theme}.webp", "WEBP", quality=85, method=6)
        files[f"base_{theme}"] = f"base_{theme}.png"
        files[f"base_{theme}_webp"] = f"base_{theme}.webp"
    del weights
    Image.fromarray(np.round(shade * 255).astype("uint8"), "L").save(out / "hillshade.png", optimize=True)
    n = neutral(shade)
    Image.fromarray(n, "L").save(out / "shade.png", optimize=True)
    Image.fromarray(n, "L").save(out / "shade.webp", "WEBP", quality=80, method=6)
    files.update(hillshade="hillshade.png", shade="shade.png", shade_webp="shade.webp")
    sea = z < 0
    ids = prov["land_sources"] + [s for s in prov["sea_sources"] if s not in prov["land_sources"]]
    manifest = {
        "fine_base": 1, "region": region, "name": name, "crs": a["crs"], "extent": [round(v) for v in extent], "cell_m": cell, "size": [w, h],
        "region_extent": a["extent"], "pixel": "pixel (i, j) covers x0 + i*cell .. x0 + (i+1)*cell east and y1 - (j+1)*cell .. y1 - j*cell north",
        "files": files,
        "style": f"Detuned: linear bathymetry on the {bathy} depth scale, linear land cross-blended by climate zone",
        "depth_scale": {"kind": bathy, "max_m": bt.OCEAN_MAX if bathy == "ocean" else bt.SMAX,
                        "ticks_m": [0, 1000, 2000, 3000, 4000, 5000, 6000] if bathy == "ocean" else [0, 250, 500, 1000],
                        "stops_m": bt.OCEAN_SB if bathy == "ocean" else bt.SB},
        "land_scale": {"max_m": bt.LMAX, "ticks_m": [0, 500, 1000, 1500], "stops_m": bt.LB},
        "hillshade": {"file": "hillshade.png", "flat": round(FLAT * 255), "range": [0, 255], "model": HILLSHADE_MODEL,
                      "exaggeration": exaggeration(cell), "ambient": AMBIENT, "sky_search_cells": search_cells(cell)},
        "shade": {"file": "shade.png", "webp": "shade.webp", "flat": 128, "gain": GAIN,
                  "note": "the hillshade with flat ground at mid grey and slopes stretched 2.5 x; composite with soft-light directly"},
        "stats": {"sea_share": round(float(sea.mean()), 4), "z_min_m": round(float(z.min()), 1), "z_max_m": round(float(z.max()), 1),
                  "depth_p50_m": round(float(-np.median(z[sea])), 1) if sea.any() else None,
                  "depth_p99_m": round(float(-np.percentile(z[sea], 1)), 1) if sea.any() else None,
                  "shade_p1_p99": [int(v) for v in np.percentile(n, [1, 99])]},
        "grid": {"file": "hires.tif", "cell_m": prov["cell_m"], "built": prov["built"], "land_sources": prov["land_sources"], "sea_sources": prov["sea_sources"]},
        "sources": [{"id": i, "name": sources[i]["name"], "res_m": sources[i]["res_m"], "licence": sources[i]["licence"]} for i in ids],
        "attribution": prov["attribution"],
        "zones": "Beck et al. (2023) Köppen-Geiger 1991-2020, 1 km, CC BY 4.0 (land tint only)",
        "note": "Draw base_<theme> with an identity transform in `extent`, data over it, then the shade. Crop by whole cells. Do not recolour, reshade or resample. Not for navigation.",
        "built": date.today().isoformat(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("region")
    ap.add_argument("--extent", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--name", default="fine")
    args = ap.parse_args()
    m = render(args.region, args.extent, args.name)
    print(f"{args.region}/{args.name}: {m['size'][0]} x {m['size'][1]} at {m['cell_m']:g} m, extent {m['extent']}, sea {m['stats']['sea_share']:.0%}, "
          f"neutral shade 1st to 99th percentile {m['stats']['shade_p1_p99']}")
