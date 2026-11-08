"""Print layers: terrain products for one map frame, generalised for its scale. Relief owns all terrain processing.

Sheet (and any other map maker) states a region, a scale, a print dpi and optionally an extent; this script returns
the files it needs and a `layers.json` that describes them. The consumer does no contouring, shading or resampling
of terrain itself: it reads these files and draws them.

    python scripts/print_layers.py <region> --scale 1500000 --dpi 150 --out DIR
        [--extent x0,y0,x1,y1] [--layers elevation,zones,hillshade,contours,coast]
        [--source auto|tiles|hires] [--interval-sea M] [--interval-land M]

Files written to DIR (all georeferenced in the region CRS, metres):
  elevation.tif   float32 heights (m, sea negative) on the finest grid the scale can use: the coarsest tile level whose
                  cell is no coarser than one print pixel, or the finest level when none is
  zones.tif       uint8 RGB climate-zone weights (temperate, boreal, tundra; arid = remainder), as the demo texture
  hillshade.tif   uint8 shade multiplier x 100 (100 = flat, neutral; 0..160), soft multi-directional light as in
                  preview/relief.js, slopes measured over one print pixel so sub-pixel noise averages away
  contours.geojson  generalised contour lines (MultiLineString per level) with properties z (m, depth negative),
                  kind (land|sea), index (true every 5th). 0 m is excluded; blur, Douglas-Peucker, Chaikin
  coast.geojson   the 0 m line, generalised harder (skerries and noise dropped)
  layers.json     CRS, extent, scale, dpi, source level, every file with its encoding and parameters, attribution

Source `tiles` is the committed tile pyramid (data/out/<region>/tiles), so this runs anywhere the repo does; `hires`
reads data/raw/<region>/hires.tif when present. `auto` uses tiles.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import contourpy
import numpy as np
import rasterio
import render_region as rr
from rasterio.transform import from_origin
from scipy.ndimage import gaussian_filter
from shapely.geometry import LineString
from smooth import chaikin, douglas_peucker

from regions import load

ROOT = Path(__file__).resolve().parents[1]
TILE = 512
# contour intervals (sea depth m, land height m) by scale denominator: chosen so lines stay about 1.5-4 mm apart on
# typical slopes; the index contour (heavier) is every fifth
INTERVALS = [
    (250e3, 25, 50),
    (750e3, 50, 100),
    (2.5e6, 100, 200),
    (7.5e6, 250, 500),
    (float("inf"), 500, 1000),
]
SOFT_LIGHTS = 6
MIN_CELL_PX = 1.0


def intervals_for(scale: float) -> tuple[float, float]:
    for limit, sea, land in INTERVALS:
        if scale <= limit:
            return float(sea), float(land)
    raise AssertionError


# ---------------------------------------------------------------------------------------------- sources
def choose_level(levels: list[dict], pm: float) -> dict:
    """Coarsest tile level whose cell is at most one print pixel; the finest level if every level is coarser."""
    ok = [lv for lv in levels if lv["cell"] <= pm * MIN_CELL_PX]
    return (
        min(ok, key=lambda lv: -lv["cell"])
        if ok
        else min(levels, key=lambda lv: lv["cell"])
    )


def read_tiles(
    region: str, extent: tuple[float, float, float, float], pm: float
) -> tuple[np.ndarray, rasterio.Affine, dict]:
    """Heights covering `extent` from the tile pyramid, snapped out to whole cells of the chosen level."""
    d = ROOT / "data" / "out" / region / "tiles"
    meta = json.loads((d / "tiles.json").read_text())
    lv = choose_level(meta["levels"], pm)
    cell, (w, h) = lv["cell"], lv["size"]
    x0, _, _, y1 = meta["extent"]
    ex0, ey0, ex1, ey1 = extent
    i0, i1 = max(0, math.floor((ex0 - x0) / cell)), min(w, math.ceil((ex1 - x0) / cell))
    j0, j1 = max(0, math.floor((y1 - ey1) / cell)), min(h, math.ceil((y1 - ey0) / cell))
    if i1 <= i0 or j1 <= j0:
        raise SystemExit(
            f"extent {extent} is outside region {region} ({meta['extent']})"
        )
    out = np.zeros((j1 - j0, i1 - i0), dtype="float32")
    for ty in range(j0 // TILE, (j1 - 1) // TILE + 1):
        for tx in range(i0 // TILE, (i1 - 1) // TILE + 1):
            z = rr.decode((d / str(lv["z"]) / f"{tx}_{ty}.webp").read_bytes()).astype(
                "float32"
            )
            ta, tb = tx * TILE, ty * TILE
            a0, a1 = max(i0, ta), min(i1, ta + z.shape[1])
            b0, b1 = max(j0, tb), min(j1, tb + z.shape[0])
            out[b0 - j0 : b1 - j0, a0 - i0 : a1 - i0] = z[
                b0 - tb : b1 - tb, a0 - ta : a1 - ta
            ]
    tr = from_origin(x0 + i0 * cell, y1 - j0 * cell, cell, cell)
    return (
        out,
        tr,
        {
            "kind": "tiles",
            "level": lv["z"],
            "cell": cell,
            "built": meta.get("built"),
            "pyramid_source": meta.get("source"),
        },
    )


def read_hires(
    region: str, extent: tuple[float, float, float, float]
) -> tuple[np.ndarray, rasterio.Affine, dict]:
    from rasterio.windows import from_bounds

    with rasterio.open(ROOT / "data" / "raw" / region / "hires.tif") as r:
        win = (
            from_bounds(*extent, transform=r.transform).round_offsets().round_lengths()
        )
        z = r.read(1, window=win, boundless=True, fill_value=0).astype("float32")
        tr = r.window_transform(win)
        cell = r.res[0]
    return np.nan_to_num(z, nan=0.0), tr, {"kind": "hires", "cell": cell}


def block_mean(a: np.ndarray, f: int) -> np.ndarray:
    if f <= 1:
        return a
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).mean(axis=(1, 3), dtype=np.float32)


def at_pixel_scale(
    z: np.ndarray, tr: rasterio.Affine, pm: float
) -> tuple[np.ndarray, rasterio.Affine, float]:
    """Average heights down so that one cell is about one print pixel (never up: no invented detail)."""
    cell = tr.a
    f = round(pm / cell) if pm / cell > 1.2 else 1
    if f <= 1:
        return z, tr, cell
    return (
        block_mean(z, f),
        rasterio.Affine(cell * f, 0, tr.c, 0, -cell * f, tr.f),
        cell * f,
    )


# ---------------------------------------------------------------------------------------------- products
def soft_hillshade(
    z: np.ndarray,
    cell: float,
    az: float = 315.0,
    alt: float = 40.0,
    exag: float | None = None,
) -> np.ndarray:
    """Shade multiplier (1.0 = flat) from six lights round the compass weighted to the north-west plus sky light.

    Same model as Relief's WebGL `soft` mode (preview/relief.js). Vertical exaggeration grows with cell size, as in
    build.hillshade, so relief does not go flat at small scales.
    """
    exag = exag if exag is not None else 2.0 * max(1.0, cell / 1000)
    zz = np.nan_to_num(z, nan=0.0) * exag
    gy_s, gx = np.gradient(zz, cell)  # axis 0 runs south
    nx, ny, nz = (
        -gx,
        gy_s,
        np.ones_like(zz),
    )  # normal = (-dz/dx, -dz/dy_north, 1), dz/dy_north = -gy_s
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / norm, ny / norm, nz / norm
    ra = math.radians(alt)
    acc = np.zeros_like(zz)
    wsum = 0.0
    for k in range(SOFT_LIGHTS):
        a = math.radians(az) + k * math.pi / 3
        w = 1.0 + 0.8 * math.cos(k * math.pi / 3)
        lx, ly, lz = (
            math.sin(a) * math.cos(ra),
            math.cos(a) * math.cos(ra),
            math.sin(ra),
        )
        acc += w * np.maximum(nx * lx + ny * ly + nz * lz, 0.0)
        wsum += w
    return (acc / wsum) / max(math.sin(ra), 0.2) * 0.7 + nz * 0.3


def contour_lines(
    z: np.ndarray,
    tr: rasterio.Affine,
    levels: list[float],
    scale: float,
    sigma_px: float = 0.7,
    min_len_mm: float = 4.0,
    tol_mm: float = 0.04,
    smooth: int = 2,
) -> dict[float, list[np.ndarray]]:
    """Generalised contour lines per level in ground metres: blur, trace, Douglas-Peucker at `tol_mm`, Chaikin."""
    zs = gaussian_filter(z, sigma_px, mode="nearest") if sigma_px else z
    h, w = zs.shape
    xs = tr.c + (np.arange(w) + 0.5) * tr.a
    ys = tr.f + (np.arange(h) + 0.5) * tr.e
    gen = contourpy.contour_generator(x=xs, y=ys, z=zs)
    mm = scale / 1000.0
    out: dict[float, list[np.ndarray]] = {}
    for lv in levels:
        keep = []
        for ln in gen.lines(lv):
            if len(ln) < 4:
                continue
            if LineString(ln).length < min_len_mm * mm:
                continue
            ln = douglas_peucker(ln, tol_mm * mm)
            if smooth and len(ln) >= 4:
                ln = douglas_peucker(
                    chaikin(ln, smooth), tol_mm * 0.5 * mm
                )  # smooth, then thin the vertices Chaikin added
            keep.append(np.round(ln, 1))
        if keep:
            out[lv] = keep
    return out


def levels_for(zmin: float, zmax: float, sea: float, land: float) -> list[float]:
    lv = [-k * sea for k in range(1, int(-zmin // sea) + 1)] if zmin < 0 else []
    lv += [k * land for k in range(1, int(zmax // land) + 1)] if zmax > 0 else []
    return sorted(lv)


def feature_collection(
    lines: dict[float, list[np.ndarray]], sea: float, land: float, crs: str
) -> dict:
    feats = []
    for lv, parts in sorted(lines.items()):
        step = land if lv > 0 else sea
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "z": lv,
                    "kind": "land" if lv > 0 else "sea",
                    "index": bool(round(abs(lv) / step) % 5 == 0),
                },
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [
                        [[float(x), float(y)] for x, y in p] for p in parts
                    ],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "contours",
        "crs_note": crs,
        "features": feats,
    }


def write_tif(
    path: Path, a: np.ndarray, tr: rasterio.Affine, crs: str, dtype: str, nodata=None
) -> None:
    a = a if a.ndim == 3 else a[None]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=a.shape[2],
        height=a.shape[1],
        count=a.shape[0],
        dtype=dtype,
        crs=crs,
        transform=tr,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
        predictor=3 if dtype == "float32" else 2,
        nodata=nodata,
    ) as dst:
        dst.write(a.astype(dtype))


def zones_for(region: str, out: Path, crs: str) -> dict | None:
    from PIL import Image

    d = ROOT / "data" / "out" / region / "demo"
    if not (d / "zones.png").exists():
        return None
    meta = json.loads((d / "meta.json").read_text())
    b = meta["bounds"]
    z = np.moveaxis(np.asarray(Image.open(d / "zones.png").convert("RGB")), -1, 0)
    cw, ch = (b[2] - b[0]) / z.shape[2], (b[3] - b[1]) / z.shape[1]
    write_tif(out / "zones.tif", z, from_origin(b[0], b[3], cw, ch), crs, "uint8")
    return {
        "file": "zones.tif",
        "channels": "R temperate, G boreal, B tundra; arid = 1 - sum",
        "source": meta.get("zones", {}).get("source"),
    }


# ---------------------------------------------------------------------------------------------- main
def build(
    region: str,
    scale: float,
    dpi: int,
    out: Path,
    extent=None,
    layers=("elevation", "zones", "hillshade", "contours"),
    source: str = "auto",
    interval_sea: float | None = None,
    interval_land: float | None = None,
) -> dict:
    t0 = time.perf_counter()
    reg = {r["id"]: r for r in load()["regions"]}[region]
    crs = reg["crs"]["code"]
    extent = tuple(extent or reg["extent"])
    pm = scale * 25.4 / dpi / 1000.0
    out.mkdir(parents=True, exist_ok=True)
    use_hires = source == "hires"
    z, tr, src = (
        read_hires(region, extent) if use_hires else read_tiles(region, extent, pm)
    )
    meta_demo = ROOT / "data" / "out" / region / "demo" / "meta.json"
    dm = json.loads(meta_demo.read_text()) if meta_demo.exists() else {}
    attribution = list(
        dm.get("data", {}).get("attribution") or dm.get("attribution") or []
    )
    zs, ztr, zcell = at_pixel_scale(z, tr, pm)
    manifest: dict = {
        "relief_layers": 1,
        "region": region,
        "crs": crs,
        "extent": list(extent),
        "scale": scale,
        "dpi": dpi,
        "m_per_px": pm,
        "source": src,
        "attribution": attribution,
        "files": {},
    }
    if "elevation" in layers:
        write_tif(out / "elevation.tif", z, tr, crs, "float32")
        manifest["files"]["elevation"] = {
            "file": "elevation.tif",
            "unit": "m",
            "cell": tr.a,
            "note": "sea negative; cells as in the source level",
        }
    if "zones" in layers:
        zi = zones_for(region, out, crs)
        if zi:
            manifest["files"]["zones"] = zi
    if "hillshade" in layers:
        sh = soft_hillshade(zs, zcell)
        write_tif(
            out / "hillshade.tif",
            np.clip(np.round(sh * 100), 0, 160),
            ztr,
            crs,
            "uint8",
        )
        manifest["files"]["hillshade"] = {
            "file": "hillshade.tif",
            "encoding": "uint8 = multiplier x 100 (100 flat)",
            "cell": zcell,
            "mode": "soft",
            "az": 315,
            "alt": 40,
            "exaggeration": 2.0 * max(1.0, zcell / 1000),
        }
    sea_i, land_i = intervals_for(scale)
    sea_i, land_i = interval_sea or sea_i, interval_land or land_i
    if "contours" in layers or "coast" in layers:
        cz, ctr, ccell = at_pixel_scale(
            z, tr, pm * 0.5
        )  # contours trace on a grid at least as fine as half a pixel
    if "contours" in layers:
        lines = contour_lines(
            cz, ctr, levels_for(float(cz.min()), float(cz.max()), sea_i, land_i), scale
        )
        (out / "contours.geojson").write_text(
            json.dumps(
                feature_collection(lines, sea_i, land_i, crs), separators=(",", ":")
            )
        )
        manifest["files"]["contours"] = {
            "file": "contours.geojson",
            "interval_sea_m": sea_i,
            "interval_land_m": land_i,
            "index_every": 5,
            "levels": len(lines),
            "lines": sum(len(v) for v in lines.values()),
            "trace_cell": ccell,
            "generalisation": "gaussian 0.7 cell, Douglas-Peucker 0.04 mm, Chaikin x2, drop < 4 mm",
        }
    if "coast" in layers:
        lines = contour_lines(
            cz, ctr, [0.0], scale, sigma_px=1.2, min_len_mm=8.0, tol_mm=0.08
        )
        coast = feature_collection(lines, sea_i, land_i, crs)
        for f in coast["features"]:
            f["properties"] = {"kind": "coast"}
        (out / "coast.geojson").write_text(json.dumps(coast, separators=(",", ":")))
        manifest["files"]["coast"] = {
            "file": "coast.geojson",
            "lines": sum(len(v) for v in lines.values()),
            "generalisation": "gaussian 1.2 cell, Douglas-Peucker 0.08 mm, Chaikin x2, drop < 8 mm",
        }
    manifest["seconds"] = round(time.perf_counter() - t0, 2)
    (out / "layers.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("region")
    p.add_argument("--scale", type=float, required=True)
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--extent", help="x0,y0,x1,y1 in region CRS metres (default: the region)"
    )
    p.add_argument("--layers", default="elevation,zones,hillshade,contours")
    p.add_argument("--source", choices=["auto", "tiles", "hires"], default="auto")
    p.add_argument("--interval-sea", type=float)
    p.add_argument("--interval-land", type=float)
    a = p.parse_args()
    m = build(
        a.region,
        a.scale,
        a.dpi,
        a.out,
        [float(v) for v in a.extent.split(",")] if a.extent else None,
        tuple(a.layers.split(",")),
        a.source,
        a.interval_sea,
        a.interval_land,
    )
    print(
        f"{a.region} 1:{a.scale:,.0f} {a.dpi} dpi: source {m['source']['kind']} level cell {m['source']['cell']:g} m, {m['seconds']} s"
    )
    for k, v in m["files"].items():
        print(f"  {k}: {v['file']}")


if __name__ == "__main__":
    main()
