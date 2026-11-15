"""Fine windows of the EMODnet Bathymetry DTM at (or near) its native cell, written in a frame's CRS.

The frames' merged grids are 15 arc-seconds (about 270 m) or coarser; a ridge's width, a canyon's width and a levee's height
need EMODnet's own 1/16 arc-minute (about 115 m). A window is not a frame: it is one small GeoTIFF per scene.

  python scripts/window.py list                                         # windows in regions/windows.json
  python scripts/window.py run norfolk_banks [name ...] | --all         # fetch and write them
  python scripts/window.py box <frame> W S E N --cell 115 --name NAME   # an ad hoc lon/lat box

Output: data/raw/<frame>/windows/<name>.tif (float32 metres, + up / - down, frame CRS, NaN where EMODnet has no data) and
<name>.json (cell, extent, source, licence, attribution, date). Fetching is by 2-degree WCS chunks like build_hires.py.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from areas import AREAS
from fetch_region import EMODNET_BOX, EMODNET_PX, emodnet_chunk
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "regions" / "windows.json"
NATIVE_M = 1852 / 16  # one EMODnet pixel in latitude, 115.75 m
ATTRIBUTION = "EMODnet Bathymetry Consortium (2024): EMODnet Digital Bathymetry (DTM)"
LICENCE = "Open; cite EMODnet Bathymetry Consortium (2024)"
MARGIN_PX = 40  # source pixels read beyond the window so reprojection has no edge
CHUNK = 2 * EMODNET_PX  # the service refuses requests over about 2 degrees


def lonlat_mosaic(w: float, s: float, e: float, n: float) -> tuple[np.ndarray, rasterio.Affine]:
    """Full-resolution EMODnet depths for a lon/lat box on the 1/960-degree lattice, fetched in 2-degree chunks."""
    w0, s0 = math.floor(max(w, EMODNET_BOX[0]) * EMODNET_PX), math.floor(max(s, EMODNET_BOX[1]) * EMODNET_PX)
    e0, n0 = math.ceil(min(e, EMODNET_BOX[2]) * EMODNET_PX), math.ceil(min(n, EMODNET_BOX[3]) * EMODNET_PX)
    out = np.full((n0 - s0, e0 - w0), np.nan, dtype="float32")
    for ys in range(s0, n0, CHUNK):
        for xs in range(w0, e0, CHUNK):
            x1, y1 = min(xs + CHUNK, e0), min(ys + CHUNK, n0)
            out[n0 - y1:n0 - ys, xs - w0:x1 - w0] = _chunk(xs, ys, x1, y1)
    return out, from_origin(w0 / EMODNET_PX, n0 / EMODNET_PX, 1 / EMODNET_PX, 1 / EMODNET_PX)


def _chunk(x0: int, y0: int, x1: int, y1: int, depth: int = 0) -> np.ndarray:
    """One lattice box (pixel units) as an array; split in two when the service refuses it or answers the wrong shape."""
    arr = emodnet_chunk(x0 / EMODNET_PX, y0 / EMODNET_PX, x1 / EMODNET_PX, y1 / EMODNET_PX)
    if arr is not None and arr.shape == (y1 - y0, x1 - x0):
        return arr
    if depth >= 4 or min(x1 - x0, y1 - y0) < 2:
        raise RuntimeError(f"EMODnet refused lon {x0 / EMODNET_PX}..{x1 / EMODNET_PX}, lat {y0 / EMODNET_PX}..{y1 / EMODNET_PX}")
    if x1 - x0 >= y1 - y0:
        m = (x0 + x1) // 2
        return np.hstack([_chunk(x0, y0, m, y1, depth + 1), _chunk(m, y0, x1, y1, depth + 1)])
    m = (y0 + y1) // 2
    return np.vstack([_chunk(x0, m, x1, y1, depth + 1), _chunk(x0, y0, x1, m, depth + 1)])


def build(frame: str, name: str, bounds: tuple[float, float, float, float], cell: float, extra: dict | None = None) -> Path:
    """Write the window for projected bounds (x0, y0, x1, y1) in the frame's CRS, snapped outwards to whole cells."""
    crs = AREAS[frame]["crs"]
    x0, y0, x1, y1 = (math.floor(bounds[0] / cell) * cell, math.floor(bounds[1] / cell) * cell,
                      math.ceil(bounds[2] / cell) * cell, math.ceil(bounds[3] / cell) * cell)
    w, s, e, n = transform_bounds(crs, "EPSG:4326", x0, y0, x1, y1, densify_pts=41)
    pad = MARGIN_PX / EMODNET_PX
    src, src_tr = lonlat_mosaic(w - pad, s - pad, e + pad, n + pad)
    nx, ny = round((x1 - x0) / cell), round((y1 - y0) / cell)
    dst_tr = from_origin(x0, y1, cell, cell)
    z = np.full((ny, nx), np.nan, dtype="float32")
    native_ew = NATIVE_M * math.cos(math.radians((s + n) / 2))
    method = Resampling.average if cell >= 1.5 * NATIVE_M else Resampling.bilinear
    reproject(src, z, src_transform=src_tr, src_crs="EPSG:4326", src_nodata=np.nan, dst_transform=dst_tr, dst_crs=crs,
              dst_nodata=np.nan, resampling=method)
    out = ROOT / "data" / "raw" / frame / "windows"
    out.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out / f"{name}.tif", "w", driver="GTiff", dtype="float32", count=1, width=nx, height=ny, crs=crs,
                       transform=dst_tr, nodata=np.nan, compress="deflate", predictor=3) as d:
        d.write(z, 1)
    ok = np.isfinite(z)
    prov = {"name": name, "frame": frame, "crs": crs, "cell_m": cell, "size": [nx, ny], "extent": [x0, y0, x1, y1],
            "lonlat_bounds": [round(v, 5) for v in (w, s, e, n)], "source": "EMODnet Bathymetry DTM 2024 (emodnet__mean WCS)",
            "source_cell": f"1/16 arc-minute: {NATIVE_M:.0f} m north-south, {native_ew:.0f} m east-west at the window's centre",
            "resampling": method.name, "attribution": ATTRIBUTION, "licence": LICENCE, "built": date.today().isoformat(),
            "valid_share": round(float(ok.mean()), 4), "z_min": float(np.nanmin(z)) if ok.any() else None,
            "z_max": float(np.nanmax(z)) if ok.any() else None, "units": "metres, up positive (depths negative)"}
    prov.update(extra or {})
    (out / f"{name}.json").write_text(json.dumps(prov, indent=1) + "\n")
    print(f"  {frame}/windows/{name}.tif {nx} x {ny} at {cell:g} m, {prov['valid_share']:.0%} valid, z {prov['z_min']:.0f} to {prov['z_max']:.0f} m")
    return out / f"{name}.tif"


def run_named(w: dict, cell: float) -> Path:
    crs = AREAS[w["frame"]]["crs"]
    cx, cy = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(*w["centre"])
    half = w["size_km"] * 500
    return build(w["frame"], w["name"], (cx - half, cy - half, cx + half, cy + half), cell,
                 {"centre": w["centre"], "size_km": w["size_km"], "setting": w.get("setting")})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("names", nargs="*")
    r.add_argument("--all", action="store_true")
    r.add_argument("--cell", type=float, default=115)
    b = sub.add_parser("box")
    b.add_argument("frame")
    for k in ("west", "south", "east", "north"):
        b.add_argument(k, type=float)
    b.add_argument("--cell", type=float, default=115)
    b.add_argument("--name", required=True)
    a = ap.parse_args()
    wins = json.loads(WINDOWS.read_text())["windows"]
    if a.cmd == "list":
        for w in wins:
            print(f"{w['name']:20s} {w['frame']:16s} {w['size_km']:>4} km at {w['centre']}  {w['setting']}")
    elif a.cmd == "run":
        todo = wins if a.all else [w for w in wins if w["name"] in a.names]
        if not todo:
            sys.exit("name a window or use --all (see `list`)")
        for w in todo:
            run_named(w, a.cell)
    else:
        crs = AREAS[a.frame]["crs"]
        x0, y0, x1, y1 = transform_bounds("EPSG:4326", crs, a.west, a.south, a.east, a.north, densify_pts=41)
        build(a.frame, a.name, (x0, y0, x1, y1), a.cell)


if __name__ == "__main__":
    main()
