"""Build a higher-resolution elevation product per region from the source plan in regions/sources.json.

This is the slow job (hours, several GB of transfer), so it is a script with stages, it never runs by accident,
and every stage can be resumed:

  python scripts/build_hires.py plan [region ...]       # what would be fetched and why: no network, no files
  python scripts/build_hires.py run <region> [options]  # fetch -> merge -> render

  --stage fetch|merge|render|all   run one stage (default all)
  --cell METRES                    merged grid cell (default: web_cell_m.hires from sources.json)
  --only id,id                     restrict to these source ids
  --include-unverified             also try sources whose endpoint was not confirmed
  --force                          redo stages even when their output exists

Principles
- Fetch DECIMATED: every adapter reads or averages down to the target cell as it goes, so a 0.25 m lidar
  mosaic or 25 m sea-floor cells never sit on disk at full resolution (10 GB disk).
- Priority lists per region (regions/sources.json): finest first. Sources are blended coarse to fine with a
  feathered seam (as seabed.py does), so seams do not show as steps in the stepped or linear colour.
- Land comes from the land list, sea from the sea list; a cell is land where the land surface is above 0.5 m.
- Outputs: data/raw/<region>/hires/<source>/ (decimated pieces + DONE.json), data/raw/<region>/hires.tif
  (float32, region CRS, region extent, cell metres), hires.json (provenance, shares, attributions) and
  hires_sources.png (index of the sea source per cell). `render` then writes the page assets.

Manual sources (GEBCO, IBCAO, Danish and German models): put GeoTIFFs in data/raw/<region>/manual/<source id>/.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import shutil
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import partial
from pathlib import Path

import numpy as np
import rasterio
import requests
from areas import AREAS
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds
from scipy.ndimage import distance_transform_edt
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "regions" / "sources.json").read_text())
SOURCES = PLAN["sources"]
FEATHER_M = 1500
NODATA_LIMIT = 2e4  # heights beyond +-20 km are nodata sentinels


# --------------------------------------------------------------------------- plan
def intersects(a, b) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def manual_dir(region: str, sid: str) -> Path:
    return ROOT / "data" / "raw" / region / "manual" / sid


def hires_dir(region: str) -> Path:
    return ROOT / "data" / "raw" / region / "hires"


def make_plan(region: str, only=None, include_unverified=False) -> list[dict]:
    """Ordered steps (finest first, per kind) with whether each can run now and why not."""
    spec, area = PLAN["regions"][region], AREAS[region]
    steps = []
    for kind in ("land", "sea"):
        for rank, sid in enumerate(spec[kind]):
            s = SOURCES[sid]
            step = {"kind": kind, "rank": rank, "id": sid, "name": s["name"], "res_m": s["res_m"], "adapter": s["adapter"],
                    "status": s["status"], "runnable": True, "why": ""}
            if only and sid not in only:
                step.update(runnable=False, why="not in --only")
            elif not intersects(area["box"], s.get("bbox", [-180, -90, 180, 90])):
                step.update(runnable=False, why="outside this region")
            elif s["adapter"] == "manual":
                n = len(list(manual_dir(region, sid).glob("*.tif"))) if manual_dir(region, sid).exists() else 0
                if not n:
                    step.update(runnable=False, why=f"manual: put GeoTIFFs in data/raw/{region}/manual/{sid}/ ({s.get('url', 'see regions/sources.json')})")
            elif s["status"] == "unverified" and not include_unverified:
                step.update(runnable=False, why="unverified endpoint (use --include-unverified)")
            steps.append(step)
    return steps


def print_plan(region: str, **kw) -> None:
    spec = PLAN["regions"][region]
    cell = spec["web_cell_m"]["hires"]
    x0, y0, x1, y1 = AREAS[region]["extent"]
    w, h = math.ceil((x1 - x0) / cell), math.ceil((y1 - y0) / cell)
    print(f"\n{region}: {AREAS[region]['name']}\n  frame {(x1 - x0) / 1000:,.0f} x {(y1 - y0) / 1000:,.0f} km at {cell} m "
          f"= {w} x {h} cells ({w * h / 1e6:.1f} M); now {spec['web_cell_m']['now']} m")
    print(f"  gain: {spec['gain']}")
    for st in make_plan(region, **kw):
        mark = "run " if st["runnable"] else "skip"
        print(f"  {mark} {st['kind']:4s} #{st['rank']} {st['id']:26s} {st['res_m']:>6} m  {st['adapter']:18s} {st['status']:10s} {st['why']}")


# --------------------------------------------------------------------------- grid
def region_grid(region: str, cell: float):
    a = AREAS[region]
    x0, y0, x1, y1 = a["extent"]
    w, h = math.ceil((x1 - x0) / cell), math.ceil((y1 - y0) / cell)
    return rasterio.Affine(cell, 0, x0, 0, -cell, y1), w, h


def lonlat_bounds_of(region: str) -> tuple[float, float, float, float]:
    return tuple(AREAS[region]["box"])


def save_tif(path: Path, arr: np.ndarray, transform, crs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", dtype="float32", count=1, width=arr.shape[1], height=arr.shape[0],
                       crs=crs, transform=transform, nodata=np.nan, compress="deflate", predictor=3) as d:
        d.write(arr.astype("float32"), 1)


def decimate_file(src: Path, dst: Path, cell_m: float) -> None:
    """Average a GeoTIFF down to about cell_m (in its own units: metres for projected CRSs) and save it."""
    with rasterio.open(src) as d:
        res = abs(d.res[0]) if d.crs and d.crs.is_projected else abs(d.res[0]) * 111_000
        k = max(1, int(cell_m / res))
        out_shape = (max(1, d.height // k), max(1, d.width // k))
        a = d.read(1, out_shape=out_shape, resampling=Resampling.average, masked=True).astype("float32").filled(np.nan)
        tr = d.transform * d.transform.scale(d.width / out_shape[1], d.height / out_shape[0])
        save_tif(dst, a, tr, d.crs)


# --------------------------------------------------------------------------- fetch adapters
def fetch_cog_tiles(region, sid, s, out: Path, cell: float) -> None:
    """One-degree COG tiles (Copernicus GLO-30/90) read through their overviews at about `cell` metres."""
    w, so, e, n = lonlat_bounds_of(region)
    step = cell / 111_320
    npx = max(1, round(1 / step))
    frame = box(*AREAS[region]["extent"]).buffer(cell * 4)
    fwd = Transformer.from_crs("EPSG:4326", AREAS[region]["crs"], always_xy=True)
    tiles = []
    for lat in range(math.floor(so), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            if -90 <= lat < 90 and tile_hits(frame, fwd, lon, lat):
                tiles.append((lat, lon))
    print(f"    {len(tiles)} candidate tiles", flush=True)

    def one(t):
        lat, lon = t
        name = s["tile_name"].format(NS="N" if lat >= 0 else "S", EW="E" if lon >= 0 else "W", lat=abs(lat), lon=abs(lon))
        dst = out / f"{name}.tif"
        if dst.exists():
            return 1
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"):
            try:
                d = rasterio.open("/vsicurl/" + s["url"].format(name=name))
            except rasterio.errors.RasterioIOError:
                return 0  # all-sea tiles do not exist
            with d:
                a = d.read(1, out_shape=(npx, npx), resampling=Resampling.average).astype("float32")
        save_tif(dst, a, from_bounds(lon, lat, lon + 1, lat + 1, npx, npx), "EPSG:4326")
        return 1

    with ThreadPoolExecutor(8) as ex:
        found = sum(ex.map(one, tiles))
    print(f"    {found} tiles written", flush=True)


def tile_hits(frame, fwd, lon, lat) -> bool:
    k = np.linspace(0, 1, 5)
    xs = np.concatenate([lon + k, np.full(5, lon + 1), lon + 1 - k, np.full(5, lon)])
    ys = np.concatenate([np.full(5, lat), lat + k, np.full(5, lat + 1), lat + 1 - k])
    px, py = fwd.transform(xs, ys)
    from shapely.geometry import Polygon
    return frame.intersects(Polygon(np.column_stack([px, py])).buffer(0))


def fetch_cog_vrt(region, sid, s, out: Path, cell: float) -> None:
    """A VRT index of COG tiles (ArcticDEM): one decimated read of the region's window in the source CRS."""
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"), rasterio.open("/vsicurl/" + s["url"]) as d:
        b = transform_bounds(AREAS[region]["crs"], d.crs, *AREAS[region]["extent"], densify_pts=101)
        b = (max(b[0], d.bounds.left), max(b[1], d.bounds.bottom), min(b[2], d.bounds.right), min(b[3], d.bounds.top))
        if b[0] >= b[2] or b[1] >= b[3]:
            print("    no overlap")
            return
        win = rasterio.windows.from_bounds(*b, transform=d.transform)
        shape = (max(1, round((b[3] - b[1]) / cell)), max(1, round((b[2] - b[0]) / cell)))
        a = d.read(1, window=win, out_shape=shape, resampling=Resampling.average, masked=True).astype("float32").filled(np.nan)
        a[a < -500] = np.nan  # ArcticDEM nodata is -9999
        save_tif(out / "window.tif", a, from_bounds(*b, shape[1], shape[0]), d.crs)
    print(f"    window {shape[1]} x {shape[0]}", flush=True)


def fetch_wcs_chunks(region, sid, s, out: Path, cell: float) -> None:
    """EMODnet: 2-degree full-resolution chunks, each averaged to about `cell` and written as its own small GeoTIFF."""
    from fetch_region import (
        EMODNET_BOX,
        EMODNET_PX,
        block_mean,
        emodnet_chunk,
        frame_hits,
    )
    divisors = [d for d in range(1, 65) if 1920 % d == 0]  # source pixels per output cell must divide a 2-degree chunk
    want = max(1.0, cell / 111_320 * EMODNET_PX)
    k = min(divisors, key=lambda d: abs(d - want))
    step = k / EMODNET_PX
    fwd = Transformer.from_crs("EPSG:4326", AREAS[region]["crs"], always_xy=True)
    frame = box(*AREAS[region]["extent"]).buffer(cell * 4)
    w, so, e, n = lonlat_bounds_of(region)
    w, e, so, n = max(w, EMODNET_BOX[0]), min(e, EMODNET_BOX[2]), max(so, EMODNET_BOX[1]), min(n, EMODNET_BOX[3])
    jobs = []
    lat = math.floor(so / 2) * 2
    while lat < n:
        width = 2 if lat < 62 else 4
        lon = math.floor(w / width) * width
        while lon < e:
            if frame_hits(frame, fwd, (lon, lat, lon + width, lat + 2)) and not (out / f"emodnet_{lon}_{lat}.tif").exists():
                jobs.append((lon, lat, lon + width, lat + 2))
            lon += width
        lat += 2
    print(f"    {len(jobs)} chunks of 2 degrees, {k} source px per cell ({step * 111_320:.0f} m)", flush=True)

    def one(job, depth=0):
        x0, y0, x1, y1 = job
        x0c, x1c = max(x0, EMODNET_BOX[0]), min(x1, EMODNET_BOX[2])
        arr = emodnet_chunk(x0c, y0, x1c, y1)
        if arr is None:  # refused: halve along the longer side (cells stay aligned: halves fall on multiples of k pixels)
            if depth >= 3:
                return 0
            if (x1c - x0c) >= (y1 - y0):
                mid = x0c + (x1c - x0c) / 2
                return one((x0c, y0, mid, y1), depth + 1) + one((mid, y0, x1c, y1), depth + 1)
            mid = y0 + (y1 - y0) / 2
            return one((x0c, y0, x1c, mid), depth + 1) + one((x0c, mid, x1c, y1), depth + 1)
        block = block_mean(arr, k)
        save_tif(out / f"emodnet_{x0}_{y0}_{depth}_{round(x0c * 1000)}_{round(y0 * 1000)}.tif", block,
                 rasterio.transform.from_origin(x0c, y1, step, step), "EPSG:4326")
        return 1

    done = 0
    with ThreadPoolExecutor(3) as ex:
        for i, r in enumerate(ex.map(one, jobs), start=1):
            done += r
            if i % 10 == 0:
                print(f"    {i}/{len(jobs)} chunks", flush=True)
    print(f"    {done} pieces written", flush=True)


def fetch_opendap(region, sid, s, out: Path, cell: float) -> None:
    """ETOPO 2022 over OPeNDAP: the region's window, block-averaged to about `cell` (never sampled), in bands of rows."""
    import netCDF4
    d = netCDF4.Dataset(s["url"])
    z, lat, lon = d.variables["z"], d.variables["lat"][:], d.variables["lon"][:]
    res = 1 / 60
    f = max(1, round(cell / 111_320 / res))
    w, so, e, n = lonlat_bounds_of(region)
    c0, c1 = max(0, int((w - lon[0]) / res)), min(len(lon), math.ceil((e - lon[0]) / res) + 1)
    r0, r1 = max(0, int((so - lat[0]) / res)), min(len(lat), math.ceil((n - lat[0]) / res) + 1)
    c1 -= (c1 - c0) % f
    band = (600 // f) * f
    print(f"    ETOPO rows {r0}:{r1} cols {c0}:{c1}, average {f} x {f}", flush=True)
    for r in range(r0, r1, band):
        rr = min(r + band, r1) - ((min(r + band, r1) - r) % f)
        if rr <= r:
            continue
        dst = out / f"etopo_{r}.tif"
        if dst.exists():
            continue
        a = np.ma.filled(z[r:rr, c0:c1], np.nan).astype("float32")
        blk = block_mean_local(a, f)[::-1]  # the file runs south to north
        save_tif(dst, blk, rasterio.transform.from_origin(lon[c0] - res / 2, lat[rr - 1] + res / 2, res * f, res * f), "EPSG:4326")
    d.close()


def block_mean_local(a: np.ndarray, k: int) -> np.ndarray:
    if k == 1:
        return a
    h, w = a.shape[0] // k * k, a.shape[1] // k * k
    with np.errstate(all="ignore"):
        return np.nanmean(a[:h, :w].reshape(h // k, k, w // k, k), axis=(1, 3)).astype("float32")


def read_band(d, r0: int, r1: int, c0: int, c1: int, k: int) -> np.ndarray:
    """Rows r0:r1, columns c0:c1 of an open raster, block-averaged k x k (reads the rows contiguously)."""
    return d.read(1, window=((r0, r1), (c0, c1)), out_shape=((r1 - r0) // k, (c1 - c0) // k), resampling=Resampling.average).astype("float32")


def fetch_remote_tiles(region, sid, s, out: Path, cell: float) -> None:
    """A global grid served as uncompressed GeoTIFF tiles over HTTP (GEBCO 2026 on CEDA: 90 x 90 degree int16 tiles).

    Each tile is read in bands of full-width rows (contiguous, so range requests are efficient), averaged down to about
    `cell` as it arrives, cropped to the region's longitudes and kept only if it touches the region's frame: the 933 MB
    tiles never sit on disk. Bands outside the region's latitudes are not requested. Bands are read by a few threads,
    each with its own dataset handle (GDAL handles are not thread-safe); finished bands are skipped on a re-run."""
    from fetch_region import frame_hits, retry
    w, so, e, n = lonlat_bounds_of(region)
    frame = box(*AREAS[region]["extent"]).buffer(cell * 4)
    fwd = Transformer.from_crs("EPSG:4326", AREAS[region]["crs"], always_xy=True)
    jobs = []
    for t in s["tiles"]:
        if not intersects((w, so, e, n), t["bbox"]):
            continue
        tw, tn, res_deg, size = t["bbox"][0], t["bbox"][3], 90 / 21600, 21600  # GEBCO tiles: 21600 cells over 90 degrees
        k = max(1, int(cell / (res_deg * 111_320)))
        band = (1500 // k) * k
        c0 = max(0, int((w - tw) / res_deg) // k * k)
        c1 = min(size, math.ceil((e - tw) / res_deg / k) * k)
        for r0 in range(0, size, band):
            r1 = min(size, r0 + band)
            r1 -= (r1 - r0) % k
            lat_top, lat_bot = tn - r0 * res_deg, tn - r1 * res_deg
            dst = out / f"{Path(t['url']).stem}_{r0}.tif"
            if r1 <= r0 or lat_bot > n or lat_top < so or dst.exists():
                continue
            lon_l, lon_r = tw + c0 * res_deg, tw + c1 * res_deg
            if frame_hits(frame, fwd, (lon_l, lat_bot, lon_r, lat_top)):
                jobs.append((t["url"], r0, r1, c0, c1, k, lon_l, lat_top, res_deg, dst))
    print(f"    {len(jobs)} bands to read (average {k} x {k})" if jobs else "    nothing to read", flush=True)

    def one(job):
        url, r0, r1, c0, c1, k, lon_l, lat_top, res_deg, dst = job
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="3",
                          GDAL_HTTP_TIMEOUT="120", CPL_VSIL_CURL_CHUNK_SIZE="33554432"):
            d = retry(partial(rasterio.open, "/vsicurl/" + url))
            with d:
                a = retry(partial(read_band, d, r0, r1, c0, c1, k))
        save_tif(dst, a, rasterio.transform.from_origin(lon_l, lat_top, res_deg * k, res_deg * k), "EPSG:4326")
        return 1

    done = 0
    with ThreadPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(one, jobs), start=1):
            done += r
            if i % 5 == 0 or i == len(jobs):
                print(f"    {i}/{len(jobs)} bands", flush=True)


def fetch_zip_clip(region, sid, s, out: Path, cell: float) -> None:
    """A big zipped GeoTIFF (IBCAO v5.2, 400 m): stream to disk, clip to the region window at `cell`, delete the rest."""
    zp = out / "download.zip"
    if not zp.exists():
        print(f"    downloading {s['url'].split('/')[-1].split('?')[0]} ...", flush=True)
        with requests.get(s["url"], stream=True, timeout=1800) as r:
            r.raise_for_status()
            with open(zp, "wb") as f:
                f.writelines(r.iter_content(1 << 22))
    z = zipfile.ZipFile(zp)
    member = next(n for n in z.namelist() if n.lower().endswith((".tif", ".tiff")))
    tmp = out / "_tmp"
    z.extract(member, tmp)
    z.close()
    zp.unlink()
    src = tmp / member
    with rasterio.open(src) as d:
        b = transform_bounds(AREAS[region]["crs"], d.crs, *AREAS[region]["extent"], densify_pts=101)
        b = (max(b[0], d.bounds.left), max(b[1], d.bounds.bottom), min(b[2], d.bounds.right), min(b[3], d.bounds.top))
        if b[0] >= b[2] or b[1] >= b[3]:
            print("    no overlap")
        else:
            win = rasterio.windows.from_bounds(*b, transform=d.transform).round_offsets().round_lengths()
            res = abs(d.res[0])
            k = max(1, int(cell / res))
            shape = (max(1, int(win.height) // k), max(1, int(win.width) // k))
            a = d.read(1, window=win, out_shape=shape, resampling=Resampling.average, masked=True).astype("float32").filled(np.nan)
            a[a > 1e4] = np.nan
            save_tif(out / "window.tif", a, rasterio.windows.transform(win, d.transform) * rasterio.Affine.scale(int(win.width) / shape[1], int(win.height) / shape[0]), d.crs)
            print(f"    window {shape[1]} x {shape[0]}", flush=True)
    src.unlink()
    for p in sorted(tmp.rglob("*"), reverse=True):
        p.rmdir() if p.is_dir() else None
    tmp.rmdir()


def fetch_geonorge(region, sid, s, out: Path, cell: float) -> None:
    """Geonorge download API: single-area datasets, or half-degree 'celle' grids (Kartverket sea floor). Decimated on arrival."""
    from fetch_kartverket_sea import API, cells_for
    uuid = s["uuid"]
    crs_code = "25833"
    if "area" in s:
        areas = [{"code": s["area"]["code"], "type": s["area"]["type"], "name": s["area"]["code"]}]
    else:
        avail = {a["code"] for a in requests.get(f"{API}/codelists/area/{uuid}", timeout=60).json()}
        areas = [{"code": c, "type": s.get("cell_type", "celle"), "name": c} for c in cells_for(lonlat_bounds_of(region)) if c in avail]
    todo = [a for a in areas if not list(out.glob(f"{a['code']}*.tif"))]
    print(f"    {len(areas)} areas, {len(todo)} to order", flush=True)
    for i in range(0, len(todo), 12):  # small orders: each zip is held in memory
        order = {"orderLines": [{"metadataUuid": uuid, "areas": todo[i:i + 12], "projections": [{"code": crs_code}], "formats": [{"name": "TIFF"}]}]}
        r = requests.post(f"{API}/order", json=order, timeout=120)
        r.raise_for_status()
        for f in r.json()["files"]:
            z = zipfile.ZipFile(io.BytesIO(requests.get(f["downloadUrl"], timeout=900).content))
            tmp = out / "_tmp"
            z.extractall(tmp)
            for t in tmp.rglob("*.tif"):
                decimate_file(t, out / t.name, cell)
                t.unlink()


def os_grid_square(ref: str) -> tuple[float, float, float, float] | None:
    """Bounds (E0, N0, E1, N1, British National Grid metres) of an OS 10 km tile reference such as 'hp40' or 'NT34'."""
    m = re.match(r"^([A-Za-z]{2})(\d)(\d)", ref)
    if not m:
        return None
    l1, l2 = (ord(c.upper()) - 65 for c in m.group(1))
    l1, l2 = (v - 1 if v > 8 else v for v in (l1, l2))  # the grid letters skip I
    e100, n100 = ((l1 - 2) % 5) * 5 + (l2 % 5), (19 - (l1 // 5) * 5) - (l2 // 5)
    e0, n0 = e100 * 100_000 + int(m.group(2)) * 10_000, n100 * 100_000 + int(m.group(3)) * 10_000
    return e0, n0, e0 + 10_000, n0 + 10_000


def fetch_http_zip(region, sid, s, out: Path, cell: float) -> None:
    """OS Terrain 50: one national zip holding a zip per 10 km tile (named by grid reference), each with an ASCII grid.
    Only tiles inside the region are opened; they are merged and averaged to `cell`."""
    from rasterio.merge import merge
    zp = out / "download.zip"
    if not zp.exists():
        with requests.get(s["url"], stream=True, timeout=(15, 120)) as r:
            r.raise_for_status()
            with open(zp, "wb") as f:
                f.writelines(r.iter_content(1 << 20))
    b = transform_bounds(AREAS[region]["crs"], s["crs"], *AREAS[region]["extent"], densify_pts=101)
    z = zipfile.ZipFile(zp)
    inner = [n for n in z.namelist() if n.lower().endswith(".zip")]
    keep = []
    for n in inner:
        sq = os_grid_square(Path(n).name)
        if sq and intersects(b, sq):
            zi = zipfile.ZipFile(io.BytesIO(z.read(n)))
            for m in zi.namelist():
                if m.lower().endswith(".asc"):
                    zi.extract(m, out / "_asc")
                    keep.append(out / "_asc" / m)
    print(f"    {len(keep)} of {len(inner)} tiles in the frame", flush=True)
    if keep:
        srcs = [rasterio.open(p) for p in keep]
        arr, tr = merge(srcs, res=cell, resampling=Resampling.average, nodata=-9999)
        for d in srcs:
            d.close()
        a = arr[0].astype("float32")
        a[a <= -9000] = np.nan
        save_tif(out / "terrain50.tif", a, tr, s["crs"])
    shutil.rmtree(out / "_asc", ignore_errors=True)
    zp.unlink()


def fetch_wcs(region, sid, s, out: Path, cell: float) -> None:
    """Kartverket seamless terrain model: ArcGIS WCS 1.0.0 (width and height resample on the server; WCS 2.0 scaling is
    refused). 50 km squares in EPSG:25833 at `cell` metres. Squares with no land by the coarse merged.tif are skipped."""
    b = transform_bounds(AREAS[region]["crs"], s["crs"], *AREAS[region]["extent"], densify_pts=101)
    side = 50_000
    cov = transform_bounds("EPSG:4326", s["crs"], *s["bbox"], densify_pts=21)  # where Norway's model has data
    sq = [(x, y) for x in range(int(b[0] // side) * side, int(b[2]) + 1, side) for y in range(int(b[1] // side) * side, int(b[3]) + 1, side)]
    sq = [(x, y) for x, y in sq if intersects((x, y, x + side, y + side), cov) and intersects((x, y, x + side, y + side), b)]
    to_ll = Transformer.from_crs(s["crs"], "EPSG:4326", always_xy=True)
    mt = ROOT / "data" / "raw" / region / "merged.tif"
    land = rasterio.open(mt) if mt.exists() else None
    n = max(2, round(side / cell))
    todo = []
    for x, y in sq:
        if (out / f"las_dtm_{x}_{y}.tif").exists():
            continue
        if land is not None:  # a 50 km square with no land anywhere in its 3 x 3 neighbourhood of coarse cells is open sea
            lon, lat = to_ll.transform(x + side / 2, y + side / 2)
            r, c = land.index(lon, lat)
            v = land.read(1, window=rasterio.windows.Window(max(0, c - 40), max(0, r - 40), 80, 80))
            if not (v > 0).any():
                continue
        todo.append((x, y))
    print(f"    {len(todo)} squares of {side // 1000} km at {side / n:.0f} m", flush=True)

    def one(xy):
        x, y = xy
        params = {"service": "WCS", "version": "1.0.0", "request": "GetCoverage", "coverage": s["coverage"], "crs": s["crs"],
                  "bbox": f"{x},{y},{x + side},{y + side}", "width": n, "height": n, "format": "GeoTIFF"}
        for attempt in range(3):
            try:
                r = requests.get(s["url"], params=params, timeout=300)
                if r.status_code == 200 and r.content[:4] in (b"II*\x00", b"MM\x00*"):
                    (out / f"las_dtm_{x}_{y}.tif").write_bytes(r.content)
                    return 1
            except requests.RequestException:
                pass
            time.sleep(2 ** attempt)
        return 0

    if todo and not one(todo[0]):
        raise RuntimeError("Kartverket WCS 1.0.0 request failed: dropping this source")
    with ThreadPoolExecutor(4) as ex:
        kept = 1 + sum(ex.map(one, todo[1:])) if todo else 0
    print(f"    {kept} squares written", flush=True)


ADAPTERS = {"cog_tiles": fetch_cog_tiles, "cog_vrt": fetch_cog_vrt, "wcs_chunks": fetch_wcs_chunks, "opendap": fetch_opendap,
            "geonorge_download": fetch_geonorge, "http_zip": fetch_http_zip, "wcs": fetch_wcs, "zip_clip": fetch_zip_clip, "remote_tiles": fetch_remote_tiles}


def stage_fetch(region: str, cell: float, only, include_unverified: bool, force: bool) -> None:
    for st in make_plan(region, only, include_unverified):
        if not st["runnable"] or st["adapter"] == "manual":
            continue
        out = hires_dir(region) / st["id"]
        done = out / "DONE.json"
        if done.exists() and not force:
            print(f"  {st['id']}: done already")
            continue
        out.mkdir(parents=True, exist_ok=True)
        print(f"  {st['id']} ({st['adapter']}) ...", flush=True)
        t0 = time.time()
        try:
            ADAPTERS[st["adapter"]](region, st["id"], SOURCES[st["id"]], out, cell)
        except (RuntimeError, requests.RequestException, rasterio.errors.RasterioError, OSError) as e:
            print(f"    FAILED, source skipped: {e}", flush=True)
            continue
        done.write_text(json.dumps({"cell_m": cell, "date": date.today().isoformat(), "seconds": round(time.time() - t0)}))


# --------------------------------------------------------------------------- merge
def warp_pieces(files: list[Path], tr, w, h, crs, cell: float) -> np.ndarray:
    """Warp decimated pieces into the region grid (a finite cell from an earlier piece is kept).

    Each piece is warped only into the window of the grid it covers, so thousands of small pieces cost no more than
    their own area (a full-grid temporary per piece made a 24 M-cell merge take over ten minutes)."""
    out = np.full((h, w), np.nan, dtype="float32")
    for f in files:
        with rasterio.open(f) as d:
            res = abs(d.res[0]) if d.crs.is_projected else abs(d.res[0]) * 111_320
            try:
                b = transform_bounds(d.crs, crs, *d.bounds, densify_pts=21)
                c0, c1 = max(0, int((b[0] - tr.c) / cell) - 2), min(w, math.ceil((b[2] - tr.c) / cell) + 2)
                r0, r1 = max(0, int((tr.f - b[3]) / cell) - 2), min(h, math.ceil((tr.f - b[1]) / cell) + 2)
                if not all(math.isfinite(v) for v in b):
                    raise ValueError
            except (ValueError, rasterio.errors.CRSError):
                c0, c1, r0, r1 = 0, w, 0, h
            if c1 <= c0 or r1 <= r0:
                continue
            tmp = np.full((r1 - r0, c1 - c0), np.nan, dtype="float32")
            reproject(rasterio.band(d, 1), tmp, dst_transform=tr * rasterio.Affine.translation(c0, r0), dst_crs=crs, dst_nodata=np.nan,
                      tolerance=0.0, resampling=Resampling.average if cell >= res else Resampling.bilinear)
        tmp[np.abs(tmp) > NODATA_LIMIT] = np.nan
        win = out[r0:r1, c0:c1]
        out[r0:r1, c0:c1] = np.where(np.isfinite(win), win, tmp)
    return out


def blend(layers: list[tuple[str, np.ndarray]], cell: float, valid) -> tuple[np.ndarray, np.ndarray, dict]:
    """Coarse-to-fine blend. `layers` run from the coarsest to the finest; each finer layer is feathered in over
    FEATHER_M at its edge. Returns the surface, the index (1-based, 0 = none) of the layer that dominates each
    cell, and overlap statistics. `valid(a)` is the mask of cells a layer may contribute."""
    z = None
    src = None
    stats = {}
    for i, (name, a) in enumerate(layers, start=1):
        a = a() if callable(a) else a  # layers can be loaded one at a time: a region never holds them all in memory
        if z is None:
            z = np.full(a.shape, np.nan, dtype="float32")
            src = np.zeros(a.shape, dtype="uint8")
        ok = np.isfinite(a) & valid(a)
        if not ok.any():
            continue
        if not np.isfinite(z).any():  # first layer: nothing beneath to feather into
            z = np.where(ok, a, np.float32(np.nan)).astype("float32")
            src[ok] = i
            continue
        both = ok & np.isfinite(z)
        if both.sum() > 100:
            d = a[both] - z[both]
            stats[name] = {"overlap_cells": int(both.sum()), "median_diff_m": round(float(np.median(d)), 1),
                           "p90_abs_diff_m": round(float(np.percentile(np.abs(d), 90)), 1)}
        wgt = np.clip(distance_transform_edt(ok) * (cell / FEATHER_M), 0, 1).astype("float32")
        wgt[~ok] = 0
        wgt = np.where(np.isfinite(z), wgt, ok.astype("float32"))
        base = np.where(np.isfinite(z), z, a)
        z = np.where(ok, base * (1 - wgt) + a * wgt, z)
        src[ok & (wgt > 0.5)] = i
    return z, src, stats


def collect(region: str, kind: str, tr, w, h, crs, cell: float, only, include_unverified):
    """Layers for one kind, coarsest first, from fetched pieces and manual GeoTIFFs."""
    layers, used = [], []
    for st in reversed([s for s in make_plan(region, only, include_unverified) if s["kind"] == kind and s["runnable"]]):
        sid = st["id"]
        folder = manual_dir(region, sid) if st["adapter"] == "manual" else hires_dir(region) / sid
        files = sorted(folder.rglob("*.tif")) if folder.exists() else []
        if not files:
            continue
        def load(files=files, sid=sid):
            a = warp_pieces(files, tr, w, h, crs, cell)
            if SOURCES[sid].get("zero_is_nodata"):
                a[a == 0] = np.nan  # the service fills outside its coverage (and the sea) with exact zeros
            return -np.abs(a) if sid == "dk_dybdemodel_50" else a  # that model stores depth as positive or negative

        layers.append((sid, load))
        used.append(sid)
    return layers, used


def stage_merge(region: str, cell: float, only, include_unverified: bool, force: bool) -> None:
    out = ROOT / "data" / "raw" / region / "hires.tif"
    if out.exists() and not force:
        print("  hires.tif exists (use --force to redo)")
        return
    crs = AREAS[region]["crs"]
    tr, w, h = region_grid(region, cell)
    land_layers, land_used = collect(region, "land", tr, w, h, crs, cell, only, include_unverified)
    sea_layers, sea_used = collect(region, "sea", tr, w, h, crs, cell, only, include_unverified)
    if not land_layers and not sea_layers:
        raise SystemExit("nothing fetched: run the fetch stage first (or add manual files)")
    land, _, lstats = blend(land_layers, cell, valid=lambda a: np.ones(a.shape, bool)) if land_layers else (None, None, {})
    sea, sidx, sstats = blend(sea_layers, cell, valid=lambda a: a < 0) if sea_layers else (None, None, {})
    z = combine_land_sea(land, sea)
    save_tif(out, z, tr, crs)
    from PIL import Image
    if sidx is not None:
        Image.fromarray(np.where(z < 0, sidx + 1, 0).astype("uint8"), "L").save(out.with_name("hires_sources.png"), optimize=True)
    attrib = sorted({SOURCES[s]["attribution"].replace("{date}", date.today().isoformat()).replace("{year}", str(date.today().year))
                     for s in land_used + sea_used})
    shares = {}
    for name, idx in (("sea", sidx),):
        if idx is not None:
            sea_cells = z < 0
            shares[name] = {sea_used_name: round(float((idx[sea_cells] == i).mean()), 3)
                            for i, (sea_used_name, _) in enumerate(sea_layers, start=1)}
    (out.with_name("hires.json")).write_text(json.dumps({
        "region": region, "cell_m": cell, "size": [w, h], "built": date.today().isoformat(), "land_sources": land_used[::-1],
        "sea_sources": sea_used[::-1], "sea_share_by_source": shares, "overlap": {"land": lstats, "sea": sstats}, "attribution": attrib,
        "finest_source_m": min([SOURCES[s]["res_m"] for s in land_used + sea_used] or [0])}, indent=1))
    print(f"  hires.tif {w} x {h} at {cell} m; land {land_used[::-1]}, sea {sea_used[::-1]}")


def combine_land_sea(land, sea) -> np.ndarray:
    """Land where the land surface is above 0.5 m, otherwise the sea floor (at least 1 m deep: a clean 0 m coast).
    Works in place on the arrays it is given, which are not reused afterwards."""
    ref = land if land is not None else sea
    ld = np.full(ref.shape, np.nan, dtype="float32") if land is None else land
    sd = np.full(ref.shape, np.nan, dtype="float32") if sea is None else sea
    np.nan_to_num(ld, nan=-1.0, copy=False)
    is_land = ld > 0.5
    np.nan_to_num(sd, nan=-1.0, copy=False)
    np.minimum(sd, -1.0, out=sd)
    sd[is_land] = ld[is_land]
    return sd


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("regions", nargs="*")
    p.add_argument("--only")
    p.add_argument("--include-unverified", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("region")
    r.add_argument("--stage", choices=["fetch", "merge", "render", "all"], default="all")
    r.add_argument("--cell", type=float)
    r.add_argument("--only")
    r.add_argument("--include-unverified", action="store_true")
    r.add_argument("--force", action="store_true")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    if a.cmd == "plan":
        for rid in a.regions or list(PLAN["regions"]):
            print_plan(rid, only=only, include_unverified=a.include_unverified)
        return
    cell = a.cell or PLAN["regions"][a.region]["web_cell_m"]["hires"]
    print(f"{a.region}: {a.stage} at {cell} m")
    if a.stage in ("fetch", "all"):
        stage_fetch(a.region, cell, only, a.include_unverified, a.force)
    if a.stage in ("merge", "all"):
        stage_merge(a.region, cell, only, a.include_unverified, a.force)
    if a.stage in ("render", "all"):
        import render_region
        render_region.main(a.region, source="hires")


if __name__ == "__main__":
    sys.exit(main())
