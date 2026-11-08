"""Build the assets for the techniques demo page (preview/demo.html).

One elevation texture drives every raster technique in the browser (WebGL): heights are packed into a
lossless WebP as height = -2000 + (R*256 + G) * 0.5 m (16 bits, -2,000 to +30,767 m at 0.5 m steps),
so colour ramps, hillshading, illuminated contours and glacier white are shader options, not separate files.

Sources merged on a UTM 32N grid: land from Copernicus DEM GLO-90; sea floor from Kartverket's 50 m model
where it has data, otherwise the EMODnet DTM. Glacier outlines (RGI 6.0) are rasterised to a mask.
A comparison window near Bergen is cut at three source resolutions: EMODnet averaged to GEBCO's 15" grid,
EMODnet at about 115 m, and Kartverket at 50 m.

Usage: python scripts/render_demo.py <area>
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import shapely
from PIL import Image
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import reproject
from scipy.ndimage import gaussian_filter
from shapely.geometry import shape


def shp_transform(fn, g):
    return shapely.transform(g, lambda c: np.column_stack(fn(c[:, 0], c[:, 1])))

from areas import AREAS
from build import inner_rect

CELL = 200  # metres: about 1,000 x 1,300 pixels for Vestland; the shader filters smoothly between texels
CMP_CELL = 50
CMP_SIZE_KM = 36


def grid(bounds, cell):
    x0, y0, x1, y1 = bounds
    w, h = round((x1 - x0) / cell), round((y1 - y0) / cell)
    return from_origin(x0, y1, cell, cell), w, h


def warp(src_path_or_arr, dst_tr, w, h, crs, src_tr=None, src_crs=None, how=Resampling.average):
    out = np.full((h, w), np.nan, dtype="float32")
    if isinstance(src_path_or_arr, (str, Path)):
        with rasterio.open(src_path_or_arr) as s:
            reproject(rasterio.band(s, 1), out, dst_transform=dst_tr, dst_crs=crs, resampling=how,
                      src_nodata=s.nodata, dst_nodata=np.nan)
    else:
        reproject(src_path_or_arr, out, src_transform=src_tr, src_crs=src_crs, dst_transform=dst_tr, dst_crs=crs,
                  resampling=how, dst_nodata=np.nan)
    return out


def kartverket_mosaic(raw: Path):
    files = sorted((raw / "kartverket_sea50").glob("NHS-D*.tif"))
    srcs = [rasterio.open(f) for f in files]
    arr, tr = merge(srcs, nodata=99999.0)
    for s in srcs:
        s.close()
    a = arr[0].astype("float32")
    a[a > 9e4] = np.nan
    return a, tr


def copernicus_mosaic(raw: Path):
    srcs = [rasterio.open(p) for p in sorted(raw.glob("Copernicus_*.tif"))]
    arr, tr = merge(srcs)
    for s in srcs:
        s.close()
    return arr[0].astype("float32"), tr


STEP, BASE = 0.5, -2000.0


def encode(z: np.ndarray) -> bytes:
    """16-bit heights in R (high byte) and G (low byte), lossless WebP."""
    v = np.clip(np.round((np.nan_to_num(z, nan=0.0) - BASE) / STEP), 0, 65535).astype("uint32")
    rgb = np.dstack([(v >> 8) & 255, v & 255, np.zeros_like(v)]).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, "WEBP", lossless=True, quality=100, method=6)
    return buf.getvalue()


def merged(raw: Path, crs: str, tr, w, h, kv, cop, sea_from="kartverket"):
    sea_em = warp(raw / "emodnet_dtm.tif", tr, w, h, crs)
    land = warp(cop[0], tr, w, h, crs, src_tr=cop[1], src_crs="EPSG:4326")
    sea = sea_em
    if sea_from == "kartverket":
        sea_kv = warp(kv[0], tr, w, h, crs, src_tr=kv[1], src_crs="EPSG:25833")
        sea = np.where(np.isfinite(sea_kv), sea_kv, sea_em)
    z = np.where(land > 0.5, land, np.minimum(np.nan_to_num(sea, nan=-1.0), -1.0))  # sea at least 1 m deep: a clean 0 m coast
    return z, sea_em, land


def main(area: str) -> None:
    t0 = time.time()
    a = AREAS[area]
    raw = Path("data/raw") / area
    out = Path("data/out") / area / "demo"
    (out / "compare").mkdir(parents=True, exist_ok=True)
    crs = a["crs"]
    frame = inner_rect(a["box"], crs)
    b = [round(v / CELL) * CELL for v in frame.bounds]
    tr, w, h = grid(b, CELL)
    kv, cop = kartverket_mosaic(raw), copernicus_mosaic(raw)
    z, _sea_em, _land = merged(raw, crs, tr, w, h, kv, cop)
    (out / "elev.webp").write_bytes(encode(z))

    # glaciers: outlines projected and rasterised to a mask (255 = ice)
    gl = json.loads((raw / "glaciers_rgi6.geojson").read_text())["features"]
    to = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    shapes = [(shp_transform(to, shape(f["geometry"])), 255) for f in gl if f.get("geometry")]
    mask = rasterize(shapes, out_shape=(h, w), transform=tr, fill=0, dtype="uint8", all_touched=False)
    mask = (gaussian_filter(mask.astype("float32"), 0.6)).clip(0, 255).astype("uint8")  # soft edge
    Image.fromarray(mask, "L").save(out / "glacier.png", optimize=True)
    gl_area = float((mask > 127).sum()) * CELL * CELL / 1e6

    # comparison window near Bergen: the sounds and skerries north-west of the city
    cx, cy = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(4.95, 60.55)
    half = CMP_SIZE_KM * 500
    cb = [round((cx - half) / 450) * 450, round((cy - half) / 450) * 450]
    cb += [cb[0] + 2 * half, cb[1] + 2 * half]
    ctr, cw, ch = grid(cb, CMP_CELL)
    zk, _, _ = merged(raw, crs, ctr, cw, ch, kv, cop, sea_from="kartverket")
    ze, _, _ = merged(raw, crs, ctr, cw, ch, kv, cop, sea_from="emodnet")
    # GEBCO-like: average the EMODnet surface to about 450 m (15 arc-seconds), then sample back to 50 m
    gtr, gw, gh = grid(cb, 450)
    zg_coarse = warp(ze, gtr, gw, gh, crs, src_tr=ctr, src_crs=crs, how=Resampling.average)
    zg = warp(zg_coarse, ctr, cw, ch, crs, src_tr=gtr, src_crs=crs, how=Resampling.bilinear)
    # land stays identical in all three so only the sea floor differs
    landmask = zk > 0
    for name, zz in (("gebco450", zg), ("emodnet115", ze), ("kartverket50", zk)):
        zz = np.where(landmask, zk, np.minimum(zz, -0.5))
        (out / "compare" / f"{name}.webp").write_bytes(encode(zz))

    # data overlay for the 'context' case: Sodir wildcats and fields inside the frame (NLOD 2.0)
    overlay = {}
    wild = Path("../Wildcat/data/wildcats.csv")
    if wild.exists():
        import pandas as pd

        wc = pd.read_csv(wild)
        tt = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        pts = []
        for r in wc.itertuples():
            if np.isnan(r.lat):
                continue
            x, y = tt.transform(r.lon, r.lat)
            if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
                pts.append([round(x), round(y), int(r.year), int(bool(r.technical))])
        overlay["wells"] = pts
        fl = json.loads(Path("../Wildcat/data/fields.geojson").read_text())["features"]
        fields = []
        for f in fl:
            g = shp_transform(tt.transform, shape(f["geometry"])).simplify(100)
            if g.intersects(frame):
                for p in getattr(g, "geoms", [g]):
                    fields.append([[round(x), round(y)] for x, y in p.exterior.coords])
        overlay["fields"] = fields
    meta = {
        "area": area, "crs": crs, "cell": CELL, "bounds": b, "size": [w, h],
        "zmin": float(np.nanmin(z)), "zmax": float(np.nanmax(z)),
        "glaciers": {"count": len(gl), "area_km2_raster": round(gl_area), "source": "RGI 6.0 (GLIMS), CC BY 4.0"},
        "compare": {"bounds": cb, "cell": CMP_CELL, "size": [cw, ch], "sources": {
            "gebco450": "EMODnet averaged to GEBCO's 15 arc-second grid (about 450 m)",
            "emodnet115": "EMODnet DTM 2024 (about 115 m)",
            "kartverket50": "Kartverket sea-floor terrain model, 50 m"}},
        "encoding": {"base": BASE, "step": STEP, "channels": "R high byte, G low byte"},
        "files": {p.name: p.stat().st_size for p in [out / "elev.webp", out / "glacier.png", *sorted((out / "compare").glob("*.webp"))]},
        "overlay": {k: len(v) for k, v in overlay.items()},
    }
    (out / "overlay.json").write_text(json.dumps(overlay, separators=(",", ":")))
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    print(f"demo assets: {w}x{h} at {CELL} m, elev.webp {meta['files']['elev.webp'] / 1e6:.2f} MB, glaciers {len(gl)} "
          f"({gl_area:.0f} km²), compare {cw}x{ch} at {CMP_CELL} m, overlay {meta['overlay']} ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "vestland")
