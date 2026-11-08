"""Merge land and sea elevation, then generalise into fast contour layers and a hillshade per level of detail.

For each level of detail (LOD) the merged grid is resampled to the LOD's cell size (mean), smoothed, and
contoured into STACKED polygons ("layer cake"): land above 0, 100, 250 m ...; sea deeper than 0, 50, 100 m ...
Drawn bottom-up, each covers the last, so colour fills never show slivers even after simplification.
Coastline generalisation by scale: islands and lakes smaller than MIN_AREA_PX cells are dropped and
dense skerry fields are merged by a closing of CLOSE_PX cells. Coordinates are pre-projected (metres, UTM)
and rounded, so the browser draws them with an identity transform: no projection maths at render time.

Usage: python scripts/build.py <area>
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import contourpy
import numpy as np
import rasterio
from areas import AREAS
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject
from scipy.ndimage import gaussian_filter
from shapely import set_precision
from shapely.geometry import MultiPolygon, Polygon, box, mapping
from shapely.ops import unary_union

LAND = [0, 100, 250, 500, 750, 1000, 1250, 1500]
SEA = [0, 50, 100, 150, 200, 250, 300, 400, 500, 750, 1000]  # depths, metres
# Generalisation per level of detail, in CELLS: smoothing, drop features under MIN_AREA_PX cells, merge gaps under
# CLOSE_PX cells. The cell size in metres comes from the region (regions/regions.json), so one LOD name means the
# same visual treatment at any scale. Vestland: overview 1000 m, regional 250 m, detail 125 m.
LOD_RULES = {
    "overview": {"sigma": 1.2, "min_area_px": 6, "close_px": 1.5},
    "regional": {"sigma": 1.0, "min_area_px": 5, "close_px": 1.0},
    "detail": {"sigma": 0.8, "min_area_px": 4, "close_px": 0.0},
}


def lods_for(area: dict) -> dict:
    return {name: {"cell": cfg["cell"], **LOD_RULES[name]} for name, cfg in area["lods"].items()}


def load_merged(area: str, a: dict, cell: float) -> tuple[np.ndarray, rasterio.Affine]:
    """Heights on a grid of `cell` metres in the region's CRS, aligned to the top-left of its extent.

    Regions fetched by fetch_region.py have one merged lon/lat GeoTIFF (land, EMODnet sea, ETOPO fallback), warped
    here by averaging (or bilinear when the grid is finer than the source). The legacy path (Vestland) merges the
    full-resolution Copernicus tiles and EMODnet cut itself: Copernicus where it shows land, EMODnet elsewhere.
    """
    crs = a["crs"]
    raw = Path("data/raw") / area
    if (raw / "hires.tif").exists():  # the build_hires.py grid: region CRS, extent-aligned, already merged from the best sources
        x0, y0, x1, y1 = a["extent"]
        with rasterio.open(raw / "hires.tif") as src:
            hz, hc = src.read(1).astype("float32"), abs(src.res[0])
        if cell <= hc * 1.001:
            return np.nan_to_num(hz, nan=0.0), rasterio.Affine(hc, 0, x0, 0, -hc, y1)
        w, h = math.ceil((x1 - x0) / cell), math.ceil((y1 - y0) / cell)
        tr = rasterio.Affine(cell, 0, x0, 0, -cell, y1)
        z = np.full((h, w), np.nan, dtype="float32")
        reproject(hz, z, src_transform=rasterio.Affine(hc, 0, x0, 0, -hc, y1), src_crs=crs, dst_transform=tr, dst_crs=crs,
                  dst_nodata=np.nan, resampling=Resampling.average)
        return np.nan_to_num(z, nan=0.0), tr
    if (raw / "merged.tif").exists():
        x0, y0, x1, y1 = a["extent"]
        w, h = math.ceil((x1 - x0) / cell), math.ceil((y1 - y0) / cell)
        tr = rasterio.Affine(cell, 0, x0, 0, -cell, y1)
        z = np.full((h, w), np.nan, dtype="float32")
        with rasterio.open(raw / "merged.tif") as src:
            step_m = src.res[1] * 111_000
            # tolerance=0: GDAL's approximate transformer misplaces whole row bands in Equal Earth (found on `world`)
            reproject(rasterio.band(src, 1), z, dst_transform=tr, dst_crs=crs, dst_nodata=np.nan, tolerance=0.0,
                      resampling=Resampling.average if cell >= step_m else Resampling.bilinear)
        return np.nan_to_num(z, nan=0.0), tr
    with rasterio.open(raw / "emodnet_dtm.tif") as em:
        tr, w, h = calculate_default_transform(em.crs, crs, em.width, em.height, *em.bounds, resolution=cell)
        sea = np.full((h, w), np.nan, dtype="float32")
        reproject(rasterio.band(em, 1), sea, dst_transform=tr, dst_crs=crs, resampling=Resampling.average, dst_nodata=np.nan)
    tiles = [rasterio.open(p) for p in sorted(raw.glob("Copernicus_*.tif"))]
    mosaic, mtr = merge(tiles)
    for t in tiles:
        t.close()
    land = np.full((h, w), np.nan, dtype="float32")
    reproject(mosaic[0], land, src_transform=mtr, src_crs="EPSG:4326", dst_transform=tr, dst_crs=crs,
              resampling=Resampling.average, dst_nodata=np.nan)
    z = np.where(land > 0.5, land, np.minimum(sea, 0.0))
    z = np.where(np.isnan(z), sea, z)
    return z, tr


def to_geoms(lines, tr: rasterio.Affine) -> list[Polygon]:
    """contourpy filled output (outer + hole rings, OuterCode) -> shapely polygons in projected metres."""
    polys = []
    points, offsets = lines
    for pts, offs in zip(points, offsets, strict=True):
        rings = [pts[offs[i]:offs[i + 1]] for i in range(len(offs) - 1)]
        rings = [np.column_stack(tr * (r[:, 0], r[:, 1])) for r in rings if len(r) >= 4]
        if rings:
            polys.append(Polygon(rings[0], rings[1:]))
    return polys


def inner_rect(lonlat_box, crs: str):
    """Largest upright rectangle (in projected metres) inside the projected lon/lat box: no tilted edges."""
    w, s, e, n = lonlat_box
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    edge = lambda pts: [t.transform(x, y) for x, y in pts]
    k = np.linspace(0, 1, 50)
    left = edge([(w, s + (n - s) * f) for f in k]); right = edge([(e, s + (n - s) * f) for f in k])
    bottom = edge([(w + (e - w) * f, s) for f in k]); top = edge([(w + (e - w) * f, n) for f in k])
    return box(max(x for x, _ in left), max(y for _, y in bottom), min(x for x, _ in right), min(y for _, y in top))


def band(z: np.ndarray, tr, lo: float, cfg: dict, cell: float, deeper: bool, clip=None) -> MultiPolygon | Polygon:
    gen = contourpy.contour_generator(z=(-z if deeper else z), fill_type=contourpy.FillType.OuterOffset)
    geoms = to_geoms(gen.filled(lo, np.inf), tr)
    g = unary_union(geoms) if geoms else Polygon()
    if clip is not None:
        g = g.intersection(clip)
    if cfg["close_px"]:
        d = cfg["close_px"] * cell / 2
        g = g.buffer(d, join_style="round").buffer(-d, join_style="round")
    min_area = cfg["min_area_px"] * cell * cell
    parts = []
    for p in getattr(g, "geoms", [g]):
        if p.is_empty or p.area < min_area:
            continue
        holes = [h for h in p.interiors if Polygon(h).area >= min_area]
        parts.append(Polygon(p.exterior, holes))
    g = MultiPolygon(parts) if parts else Polygon()
    g = g.simplify(cell * 0.5, preserve_topology=True)
    return set_precision(g, 10.0)  # 10 m grid: compact integers, invisible at these scales


def hillshade(z: np.ndarray, cell: float, az: float = 315, alt: float = 45, exag: float | None = None) -> np.ndarray:
    """Hillshade with vertical exaggeration growing with the cell size (2 up to 1 km), or relief goes flat."""
    exag = exag if exag is not None else 2.0 * max(1.0, cell / 1000)
    zz = np.nan_to_num(z, nan=0.0) * exag
    gy, gx = np.gradient(zz, cell)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, b = np.radians(360 - az + 90), np.radians(alt)
    hs = np.sin(b) * np.cos(slope) + np.cos(b) * np.sin(slope) * np.cos(a - aspect)
    return np.clip(hs, 0, 1)


def write_png(path: Path, hs: np.ndarray) -> None:
    import struct
    import zlib

    h, w = hs.shape
    raw = b"".join(b"\x00" + (hs[i] * 255).astype("uint8").tobytes() for i in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def count_parts(g) -> int:
    return 0 if g.is_empty else len(getattr(g, "geoms", [g]))


def main(area: str) -> None:
    a = AREAS[area]
    out = Path("data/out") / area
    out.mkdir(parents=True, exist_ok=True)
    land_levels, sea_levels = a.get("levels", {}).get("land", LAND), a.get("levels", {}).get("sea", SEA)
    manifest = {"area": area, "name": a["name"], "crs": a["crs"], "extent": a["extent"], "bbox": list(a["box"]),
                "land": land_levels, "sea": sea_levels, "bathymetry": a.get("bathymetry", "shelf"), "lods": {}}
    frame = box(*a["extent"])
    for name, cfg in lods_for(a).items():
        t0 = time.time()
        z, tr = load_merged(area, a, cfg["cell"])
        zs = gaussian_filter(np.nan_to_num(z, nan=0.0), cfg["sigma"])
        feats = []
        raw_islands = None
        for lv in land_levels:
            g = band(zs, tr, lv + 1e-3 if lv == 0 else lv, cfg, cfg["cell"], deeper=False, clip=frame)
            if lv == 0:
                gen = contourpy.contour_generator(z=z if cfg["cell"] == 125 else zs, fill_type=contourpy.FillType.OuterOffset)
                raw_islands = len(gen.filled(1e-3, np.inf)[0])
            feats.append({"type": "Feature", "properties": {"kind": "land", "level": lv, "parts": count_parts(g)}, "geometry": mapping(g)})
        for lv in sea_levels:
            g = band(zs, tr, lv + 1e-3 if lv == 0 else lv, cfg, cfg["cell"], deeper=True, clip=frame)
            feats.append({"type": "Feature", "properties": {"kind": "sea", "level": -lv, "parts": count_parts(g)}, "geometry": mapping(g)})
        bounds = [round(v) for v in frame.bounds]
        grid_bounds = [tr.c, tr.f + tr.e * z.shape[0], tr.c + tr.a * z.shape[1], tr.f]
        gj = {"type": "FeatureCollection", "bbox": bounds, "features": feats}
        text = json.dumps(gj, separators=(",", ":")).replace(".0,", ",").replace(".0]", "]")
        (out / f"{name}.geojson").write_text(text)
        # hillshade cropped to the same rectangle
        c0 = int((bounds[0] - grid_bounds[0]) / cfg["cell"]); c1 = int((bounds[2] - grid_bounds[0]) / cfg["cell"])
        r0 = int((grid_bounds[3] - bounds[3]) / cfg["cell"]); r1 = int((grid_bounds[3] - bounds[1]) / cfg["cell"])
        write_png(out / f"{name}_hillshade.png", hillshade(z, cfg["cell"])[r0:r1, c0:c1])
        manifest["lods"][name] = {**cfg, "bounds": bounds, "shape": list(z.shape), "bytes": len(text),
                                  "coast_parts": feats[0]["properties"]["parts"], "coast_parts_ungeneralised": raw_islands,
                                  "seconds": round(time.time() - t0, 1)}
        print(f"{name:9s} cell {cfg['cell']:>5} m  {z.shape[1]}x{z.shape[0]}  {len(text) / 1e6:5.2f} MB  coast parts {raw_islands} -> "
              f"{feats[0]['properties']['parts']}  ({time.time() - t0:.0f} s)")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "vestland")
