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
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
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
    """EMODnet: 2-degree full-resolution chunks averaged to the grid (fetch_region.fetch_emodnet)."""
    from fetch_region import Grid, fetch_emodnet
    grid = Grid(lonlat_bounds_of(region), cell / 111_320)
    fwd = Transformer.from_crs("EPSG:4326", AREAS[region]["crs"], always_xy=True)
    arr = fetch_emodnet(grid, box(*AREAS[region]["extent"]).buffer(cell * 4), fwd)
    save_tif(out / "emodnet.tif", arr, grid.transform, "EPSG:4326")


def fetch_opendap(region, sid, s, out: Path, cell: float) -> None:
    from fetch_region import Grid, fetch_etopo
    grid = Grid(lonlat_bounds_of(region), max(cell, 1850) / 111_320)
    save_tif(out / "etopo.tif", fetch_etopo(grid), grid.transform, "EPSG:4326")


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


def fetch_http_zip(region, sid, s, out: Path, cell: float) -> None:
    """OS Terrain 50: one national zip of 10 km ASCII-grid tiles; keep only tiles in the frame, merged at `cell`."""
    from rasterio.merge import merge
    zp = out / "download.zip"
    if not zp.exists():
        with requests.get(s["url"], stream=True, timeout=900) as r:
            r.raise_for_status()
            with open(zp, "wb") as f:
                f.writelines(r.iter_content(1 << 20))
    b = transform_bounds(AREAS[region]["crs"], s["crs"], *AREAS[region]["extent"], densify_pts=101)
    z = zipfile.ZipFile(zp)
    names = [n for n in z.namelist() if n.lower().endswith(".asc")]
    keep = []
    for n in names:
        head = z.open(n).read(400).decode("ascii", "ignore").split()
        h = {head[i].lower(): float(head[i + 1]) for i in range(0, 12, 2)}
        x0, y0, cs = h["xllcorner"], h["yllcorner"], h["cellsize"]
        if intersects(b, (x0, y0, x0 + h["ncols"] * cs, y0 + h["nrows"] * cs)):
            z.extract(n, out / "_asc")
            keep.append(out / "_asc" / n)
    print(f"    {len(keep)} of {len(names)} tiles in the frame", flush=True)
    if keep:
        srcs = [rasterio.open(p) for p in keep]
        arr, tr = merge(srcs, res=cell, resampling=Resampling.average, nodata=-9999)
        for d in srcs:
            d.close()
        a = arr[0].astype("float32")
        a[a <= -9000] = np.nan
        save_tif(out / "terrain50.tif", a, tr, s["crs"])
    for p in keep:
        p.unlink()


def fetch_wcs(region, sid, s, out: Path, cell: float) -> None:
    """Kartverket seamless terrain WCS in EPSG:25833, 50 km squares requested at `cell` metres (SCALESIZE).

    Scaling support is unverified: the first request is checked, and the source is abandoned (so the next one in the
    priority list is used) if the server ignores or refuses it. Squares with no land (by the existing coarse
    merged.tif) are skipped."""
    b = transform_bounds(AREAS[region]["crs"], s["crs"], *AREAS[region]["extent"], densify_pts=101)
    side = 50_000
    land = None
    mt = ROOT / "data" / "raw" / region / "merged.tif"
    if mt.exists():
        land = rasterio.open(mt)
    n = round(side / cell)
    sq = [(x, y) for x in range(int(b[0] // side) * side, int(b[2]) + 1, side) for y in range(int(b[1] // side) * side, int(b[3]) + 1, side)]
    cov = transform_bounds("EPSG:4326", s["crs"], *s["bbox"], densify_pts=21)  # where Norway's model has data
    sq = [(x, y) for x, y in sq if intersects((x, y, x + side, y + side), cov)]
    to_ll = Transformer.from_crs(s["crs"], "EPSG:4326", always_xy=True)
    first = True
    kept = 0
    for x, y in sq:
        dst = out / f"las_dtm_{x}_{y}.tif"
        if dst.exists():
            continue
        if land is not None:
            lon, lat = to_ll.transform(x + side / 2, y + side / 2)
            r, c = land.index(lon, lat)
            win = rasterio.windows.Window(max(0, c - 40), max(0, r - 40), 80, 80)
            v = land.read(1, window=win)
            if not (v > 0).any():
                continue
        params = [("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"), ("coverageId", s["coverage"]),
                  ("subset", f"x({x},{x + side})"), ("subset", f"y({y},{y + side})"), ("format", "image/tiff"),
                  ("scalesize", f"x({n}),y({n})")]
        r = requests.get(s["url"], params=params, timeout=300)
        ok = r.status_code == 200 and r.content[:4] in (b"II*\x00", b"MM\x00*")
        if first:
            first = False
            if ok:
                with rasterio.MemoryFile(r.content) as mf, mf.open() as d:
                    ok = d.width <= n * 1.1 and d.height <= n * 1.1
            if not ok:
                raise RuntimeError("Kartverket WCS did not honour SCALESIZE: dropping this source (" + r.text[:200] + ")")
        if ok:
            dst.write_bytes(r.content)
            kept += 1
    print(f"    {kept} squares", flush=True)


ADAPTERS = {"cog_tiles": fetch_cog_tiles, "cog_vrt": fetch_cog_vrt, "wcs_chunks": fetch_wcs_chunks, "opendap": fetch_opendap,
            "geonorge_download": fetch_geonorge, "http_zip": fetch_http_zip, "wcs": fetch_wcs}


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
    """Warp decimated pieces into the region grid (later files do not overwrite earlier finite cells)."""
    out = np.full((h, w), np.nan, dtype="float32")
    for f in files:
        with rasterio.open(f) as d:
            res = abs(d.res[0]) if d.crs.is_projected else abs(d.res[0]) * 111_320
            tmp = np.full((h, w), np.nan, dtype="float32")
            reproject(rasterio.band(d, 1), tmp, dst_transform=tr, dst_crs=crs, dst_nodata=np.nan, tolerance=0.0,
                      resampling=Resampling.average if cell >= res else Resampling.bilinear)
        tmp[np.abs(tmp) > NODATA_LIMIT] = np.nan
        out = np.where(np.isfinite(out), out, tmp)
    return out


def blend(layers: list[tuple[str, np.ndarray]], cell: float, valid) -> tuple[np.ndarray, np.ndarray, dict]:
    """Coarse-to-fine blend. `layers` run from the coarsest to the finest; each finer layer is feathered in over
    FEATHER_M at its edge. Returns the surface, the index (1-based, 0 = none) of the layer that dominates each
    cell, and overlap statistics. `valid(a)` is the mask of cells a layer may contribute."""
    z = None
    src = None
    stats = {}
    for i, (name, a) in enumerate(layers, start=1):
        if z is None:
            z = np.full(a.shape, np.nan, dtype="float32")
            src = np.zeros(a.shape, dtype="uint8")
        ok = np.isfinite(a) & valid(a)
        if not ok.any():
            continue
        both = ok & np.isfinite(z)
        if both.sum() > 100:
            d = a[both] - z[both]
            stats[name] = {"overlap_cells": int(both.sum()), "median_diff_m": round(float(np.median(d)), 1),
                           "p90_abs_diff_m": round(float(np.percentile(np.abs(d), 90)), 1)}
        wgt = np.clip(distance_transform_edt(ok) * cell / FEATHER_M, 0, 1).astype("float32")
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
        a = warp_pieces(files, tr, w, h, crs, cell)
        if sid in ("dk_dybdemodel_50",):
            a = -np.abs(a)  # stored as positive or negative depth
        layers.append((sid, a))
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
    """Land where the land surface is above 0.5 m, otherwise the sea floor (at least 1 m deep: a clean 0 m coast)."""
    ref = land if land is not None else sea
    ld = np.full(ref.shape, np.nan, dtype="float32") if land is None else land
    sd = np.full(ref.shape, np.nan, dtype="float32") if sea is None else sea
    is_land = np.nan_to_num(ld, nan=-1.0) > 0.5
    sea_z = np.minimum(np.nan_to_num(sd, nan=-1.0), -1.0)
    return np.where(is_land, ld, sea_z).astype("float32")


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
