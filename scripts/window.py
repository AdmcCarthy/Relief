"""Fine windows of the EMODnet Bathymetry DTM at (or near) its native cell, written in a frame's CRS; and height windows of the
Copernicus DEM GLO-90 at its native cell anywhere on land, written in the local UTM zone.

The frames' merged grids are 15 arc-seconds (about 270 m) or coarser; a ridge's width, a canyon's width and a levee's height
need EMODnet's own 1/16 arc-minute (about 115 m). A window is not a frame: it is one small GeoTIFF per scene.

  python scripts/window.py list                                         # windows in regions/windows.json
  python scripts/window.py run norfolk_banks [name ...] | --all         # fetch and write them
  python scripts/window.py box <frame> W S E N --cell 115 --name NAME   # an ad hoc lon/lat box
  python scripts/window.py dem W S E N --name NAME [--cell 90]          # a GLO-90 height window, UTM of the box centre
  python scripts/window.py dem --all                                    # every `dem` window of regions/windows.json

Output: data/raw/<frame>/windows/<name>.tif (float32 metres, + up / - down, frame CRS, NaN where EMODnet has no data) and
<name>.json (cell, extent, source, licence, attribution, date). Fetching is by 2-degree WCS chunks like build_hires.py. A DEM
window goes to data/raw/dem/windows/<name>.tif (float32 metres above EGM2008, NaN where the tile has no data or does not
exist), read from the one-degree COG tiles of the Copernicus DEM GLO-90 on AWS (regions/sources.json `cop_glo90`) at their
native cell, mosaicked in lon/lat and reprojected once onto a UTM grid at `--cell` metres; the request for structural
scenes outside Europe is docs/plan-landforms-structure.md.
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


DEM_SOURCE = json.loads((ROOT / "regions" / "sources.json").read_text())["sources"]["cop_glo90"]


def utm_of(lon: float, lat: float) -> str:
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"


def dem_window(name: str, w: float, s: float, e: float, n: float, cell: float = 90.0, extra: dict | None = None) -> Path:
    """A Copernicus DEM GLO-90 window for a lon/lat box, reprojected onto the local UTM grid at `cell` metres."""
    from rasterio.merge import merge

    tiles, missing = [], []
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            tname = DEM_SOURCE["tile_name"].format(NS="N" if lat >= 0 else "S", EW="E" if lon >= 0 else "W", lat=abs(lat), lon=abs(lon))
            url = "/vsicurl/" + DEM_SOURCE["url"].format(name=tname)
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"):
                try:
                    tiles.append(rasterio.open(url))
                except rasterio.errors.RasterioIOError:
                    missing.append(tname)  # an all-sea tile does not exist
    if not tiles:
        raise RuntimeError(f"no GLO-90 tile covers lon {w}..{e}, lat {s}..{n}")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"):
        pad = 0.01
        src, src_tr = merge(tiles, bounds=(w - pad, s - pad, e + pad, n + pad), nodata=np.nan, dtype="float32")
        src_crs = tiles[0].crs
        for t in tiles:
            t.close()
    src = src[0]
    crs = utm_of((w + e) / 2, (s + n) / 2)
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", crs, w, s, e, n, densify_pts=41)
    x0, y0, x1, y1 = (math.floor(x0 / cell) * cell, math.floor(y0 / cell) * cell, math.ceil(x1 / cell) * cell, math.ceil(y1 / cell) * cell)
    nx, ny = round((x1 - x0) / cell), round((y1 - y0) / cell)
    dst_tr = from_origin(x0, y1, cell, cell)
    z = np.full((ny, nx), np.nan, dtype="float32")
    reproject(src, z, src_transform=src_tr, src_crs=src_crs, src_nodata=np.nan, dst_transform=dst_tr, dst_crs=crs, dst_nodata=np.nan,
              resampling=Resampling.average if cell >= 135 else Resampling.bilinear)
    out = ROOT / "data" / "raw" / "dem" / "windows"
    out.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out / f"{name}.tif", "w", driver="GTiff", dtype="float32", count=1, width=nx, height=ny, crs=crs,
                       transform=dst_tr, nodata=np.nan, compress="deflate", predictor=3) as d:
        d.write(z, 1)
    ok = np.isfinite(z)
    prov = {"name": name, "frame": "dem", "crs": crs, "cell_m": cell, "size": [nx, ny], "extent": [x0, y0, x1, y1],
            "lonlat_bounds": [round(v, 5) for v in (w, s, e, n)], "source": f"{DEM_SOURCE['name']} (one-degree COG tiles, AWS open data)",
            "source_cell": "3 arc-seconds (about 90 m north-south)", "tiles_missing": missing, "resampling": "bilinear" if cell < 135 else "average",
            "attribution": DEM_SOURCE["attribution"], "licence": DEM_SOURCE["licence"], "built": date.today().isoformat(),
            "valid_share": round(float(ok.mean()), 4), "z_min": float(np.nanmin(z)) if ok.any() else None,
            "z_max": float(np.nanmax(z)) if ok.any() else None, "units": "metres above EGM2008 (the sea has no data or is near zero)"}
    prov.update(extra or {})
    (out / f"{name}.json").write_text(json.dumps(prov, indent=1) + "\n")
    print(f"  dem/windows/{name}.tif {nx} x {ny} at {cell:g} m in {crs}, {prov['valid_share']:.0%} valid, z {prov['z_min']:.0f} to {prov['z_max']:.0f} m")
    return out / f"{name}.tif"


GEBCO_SOURCE = json.loads((ROOT / "regions" / "sources.json").read_text())["sources"]["gebco_2026"]


def gebco_window(name: str, w: float, s: float, e: float, n: float, cell: float = 450.0, extra: dict | None = None) -> Path:
    """A GEBCO_2026 window (sea floor and land, one grid) for a lon/lat box anywhere, read by HTTP range requests from the 90 degree
    tiles on CEDA (only the rows and columns of the box cross the wire), reprojected once onto a UTM grid at `cell` metres."""
    from rasterio.merge import merge
    from rasterio.windows import from_bounds as wfb

    tiles = [t for t in GEBCO_SOURCE["tiles"] if t["bbox"][0] < e and t["bbox"][2] > w and t["bbox"][1] < n and t["bbox"][3] > s]
    if not tiles:
        raise RuntimeError(f"no GEBCO tile covers lon {w}..{e}, lat {s}..{n}")
    pad = 0.05
    parts = []
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="3"):
        for t in tiles:
            with rasterio.open("/vsicurl/" + t["url"]) as d:
                bw, bs, be, bn = max(w - pad, d.bounds.left), max(s - pad, d.bounds.bottom), min(e + pad, d.bounds.right), min(n + pad, d.bounds.top)
                win = wfb(bw, bs, be, bn, transform=d.transform).round_offsets().round_lengths()
                a = d.read(1, window=win).astype("float32")
                parts.append((a, d.window_transform(win)))
    if len(parts) == 1:
        src, src_tr = parts[0]
    else:  # a box across a tile seam: write the parts to memory files and merge
        mem = []
        for a, tr in parts:
            f = rasterio.MemoryFile()
            with f.open(driver="GTiff", height=a.shape[0], width=a.shape[1], count=1, dtype="float32", crs="EPSG:4326", transform=tr) as d:
                d.write(a, 1)
            mem.append(f)
        ds = [f.open() for f in mem]
        src, src_tr = merge(ds, bounds=(w - pad, s - pad, e + pad, n + pad))
        src = src[0]
    crs = utm_of((w + e) / 2, (s + n) / 2)
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", crs, w, s, e, n, densify_pts=41)
    x0, y0, x1, y1 = (math.floor(x0 / cell) * cell, math.floor(y0 / cell) * cell, math.ceil(x1 / cell) * cell, math.ceil(y1 / cell) * cell)
    nx, ny = round((x1 - x0) / cell), round((y1 - y0) / cell)
    dst_tr = from_origin(x0, y1, cell, cell)
    z = np.full((ny, nx), np.nan, dtype="float32")
    reproject(src, z, src_transform=src_tr, src_crs="EPSG:4326", dst_transform=dst_tr, dst_crs=crs, dst_nodata=np.nan,
              resampling=Resampling.average if cell >= 1.5 * 463 else Resampling.bilinear)
    out = ROOT / "data" / "raw" / "gebco" / "windows"
    out.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out / f"{name}.tif", "w", driver="GTiff", dtype="float32", count=1, width=nx, height=ny, crs=crs,
                       transform=dst_tr, nodata=np.nan, compress="deflate", predictor=3) as d:
        d.write(z, 1)
    ok = np.isfinite(z)
    prov = {"name": name, "frame": "gebco", "crs": crs, "cell_m": cell, "size": [nx, ny], "extent": [x0, y0, x1, y1],
            "lonlat_bounds": [round(v, 5) for v in (w, s, e, n)], "source": "GEBCO_2026 Grid (ice-surface elevation, 15 arc-second GeoTIFF tiles on CEDA, range requests)",
            "source_cell": "15 arc-seconds (about 463 m at the equator)", "resampling": "average" if cell >= 1.5 * 463 else "bilinear",
            "attribution": GEBCO_SOURCE["attribution"], "licence": GEBCO_SOURCE["licence"], "built": date.today().isoformat(),
            "valid_share": round(float(ok.mean()), 4), "z_min": float(np.nanmin(z)) if ok.any() else None,
            "z_max": float(np.nanmax(z)) if ok.any() else None, "units": "metres, up positive (depths negative)"}
    prov.update(extra or {})
    (out / f"{name}.json").write_text(json.dumps(prov, indent=1) + "\n")
    print(f"  gebco/windows/{name}.tif {nx} x {ny} at {cell:g} m in {crs}, {prov['valid_share']:.0%} valid, z {prov['z_min']:.0f} to {prov['z_max']:.0f} m")
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
    d = sub.add_parser("dem")
    d.add_argument("bounds", nargs="*", type=float, help="W S E N in degrees")
    d.add_argument("--name")
    d.add_argument("--all", action="store_true", help="every window with frame `dem` in regions/windows.json")
    d.add_argument("--cell", type=float, default=90)
    g = sub.add_parser("gebco")
    g.add_argument("bounds", nargs="*", type=float, help="W S E N in degrees")
    g.add_argument("--name")
    g.add_argument("--all", action="store_true", help="every window with frame `gebco` in regions/windows.json")
    g.add_argument("--cell", type=float, default=450)
    a = ap.parse_args()
    wins = json.loads(WINDOWS.read_text())["windows"]
    if a.cmd == "list":
        for w in wins:
            print(f"{w['name']:20s} {w['frame']:16s} {w['size_km']:>4} km at {w['centre']}  {w['setting']}")
    elif a.cmd == "run":
        todo = [w for w in wins if w["frame"] not in ("dem", "gebco")] if a.all else [w for w in wins if w["name"] in a.names and w["frame"] not in ("dem", "gebco")]
        if not todo:
            sys.exit("name a window or use --all (see `list`)")
        for w in todo:
            run_named(w, a.cell)
    elif a.cmd == "gebco":
        if a.all:
            for w in [w for w in wins if w["frame"] == "gebco"]:
                half_lat = w["size_km"] / 222.0
                half_lon = half_lat / math.cos(math.radians(w["centre"][1]))
                lon, lat = w["centre"]
                gebco_window(w["name"], lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat, w.get("cell", a.cell), {"centre": w["centre"], "size_km": w["size_km"], "setting": w.get("setting")})
        else:
            if len(a.bounds) != 4 or not a.name:
                sys.exit("gebco needs W S E N and --name, or --all")
            gebco_window(a.name, *a.bounds, a.cell)
    elif a.cmd == "dem":
        if a.all:
            for w in [w for w in wins if w["frame"] == "dem"]:
                half_lat = w["size_km"] / 222.0
                half_lon = half_lat / math.cos(math.radians(w["centre"][1]))
                lon, lat = w["centre"]
                dem_window(w["name"], lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat, w.get("cell", a.cell), {"centre": w["centre"], "size_km": w["size_km"], "setting": w.get("setting")})
        else:
            if len(a.bounds) != 4 or not a.name:
                sys.exit("dem needs W S E N and --name, or --all")
            dem_window(a.name, *a.bounds, a.cell)
    else:
        crs = AREAS[a.frame]["crs"]
        x0, y0, x1, y1 = transform_bounds("EPSG:4326", crs, a.west, a.south, a.east, a.north, densify_pts=41)
        build(a.frame, a.name, (x0, y0, x1, y1), a.cell)


if __name__ == "__main__":
    main()
