"""Fetch and merge open elevation for a region at its own resolution, without downloading whole datasets.

Writes data/raw/<region>/merged.tif: float32 EPSG:4326, one cell per `fetch.step_deg`, NaN where nothing is known,
heights in metres (land positive, sea negative). Sources, in order of preference:
  land  Copernicus DEM GLO-90, read through the COG overviews of each 1-degree tile on the open AWS bucket
        (only the bytes for the coarse grid are transferred), else ETOPO 2022
  sea   EMODnet Bathymetry DTM 2024 (~115 m) from the WCS in 2-degree chunks, each averaged down to the grid
        (the service refuses larger requests and ignores WCS scaling), else ETOPO 2022
  base  NOAA ETOPO 2022 surface (60 arc-second) over OPeNDAP, for the world and for sea outside EMODnet (east of 43 E)
Chunks and tiles outside the region's projected frame are skipped. Licences: docs/sources.md.

Usage: python scripts/fetch_region.py <region> [--no-emodnet]
"""

from __future__ import annotations

import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
import requests
from areas import AREAS
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import reproject
from shapely.geometry import box

EMODNET_WCS = "https://ows.emodnet-bathymetry.eu/wcs"
EMODNET_PX = 960  # pixels per degree
EMODNET_BOX = (-70.5, 11.0, 43.0, 90.0)
COP90 = "https://copernicus-dem-90m.s3.amazonaws.com/{n}/{n}.tif"
ETOPO = "https://www.ngdc.noaa.gov/thredds/dodsC/global/ETOPO2022/60s/60s_surface_elev_netcdf/ETOPO_2022_v1_60s_N90W180_surface.nc"


class Grid:
    """Cells of `step` degrees aligned to the EMODnet pixel lattice (units of 1/960 degree, so edges are exact)."""

    def __init__(self, bbox, step_deg: float):
        self.k = max(1, round(step_deg * EMODNET_PX))
        self.step = self.k / EMODNET_PX
        w, s, e, n = bbox
        self.w0 = math.floor(max(w, -180) * EMODNET_PX / self.k) * self.k
        self.s0 = math.floor(max(s, -90) * EMODNET_PX / self.k) * self.k
        e0 = math.ceil(min(e, 180) * EMODNET_PX / self.k) * self.k
        n0 = math.ceil(min(n, 90) * EMODNET_PX / self.k) * self.k
        self.nx, self.ny = (e0 - self.w0) // self.k, (n0 - self.s0) // self.k
        self.transform = from_origin(self.w0 / EMODNET_PX, n0 / EMODNET_PX, self.step, self.step)

    def cell_lonlat(self, ix0, iy0, ix1, iy1):  # cell index ranges (iy counted from the south) -> degrees
        return [(self.w0 + ix0 * self.k) / EMODNET_PX, (self.s0 + iy0 * self.k) / EMODNET_PX,
                (self.w0 + ix1 * self.k) / EMODNET_PX, (self.s0 + iy1 * self.k) / EMODNET_PX]


def retry(fn, tries=4):
    for i in range(tries):
        try:
            return fn()
        except (OSError, RuntimeError, requests.RequestException):
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def block_mean(a: np.ndarray, k: int) -> np.ndarray:
    h, w = a.shape[0] // k * k, a.shape[1] // k * k
    b = a[:h, :w].reshape(h // k, k, w // k, k)
    with np.errstate(all="ignore"):
        return np.nanmean(b, axis=(1, 3)).astype("float32")


def emodnet_chunk(w: float, s: float, e: float, n: float) -> np.ndarray | None:
    """Full-resolution EMODnet depths for a lon/lat box as an array (north up), splitting the box if refused."""
    params = [("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"), ("coverageId", "emodnet__mean"),
              ("subset", f"Lat({s:.8f},{n:.8f})"), ("subset", f"Long({w:.8f},{e:.8f})"), ("format", "image/tiff")]
    def go():
        r = requests.get(EMODNET_WCS, params=params, timeout=600)
        if r.status_code >= 500 or not r.content.startswith((b"II*\x00", b"MM\x00*")):
            raise RuntimeError(r.status_code)
        return r.content
    try:
        content = retry(go, 3)
    except (RuntimeError, requests.RequestException):
        return None  # refused or unreachable: the caller splits the box
    with MemoryFile(content) as mf, mf.open() as d:
        return d.read(1, masked=True).astype("float32").filled(np.nan)


def fetch_emodnet(grid: Grid, frame, inv_fwd, workers: int = 3) -> np.ndarray:
    out = np.full((grid.ny, grid.nx), np.nan, dtype="float32")
    cells_lat = 2 * EMODNET_PX // grid.k  # 2 degrees of cells
    jobs = []
    iy = 0
    while iy < grid.ny:
        iy1 = min(iy + cells_lat, grid.ny)
        lat_mid = grid.cell_lonlat(0, iy, 1, iy1)[1] + 1
        cells_lon = (2 if lat_mid < 62 else 4) * EMODNET_PX // grid.k
        ix = 0
        while ix < grid.nx:
            ix1 = min(ix + cells_lon, grid.nx)
            w, s, e, n = grid.cell_lonlat(ix, iy, ix1, iy1)
            inside = e > EMODNET_BOX[0] and w < EMODNET_BOX[2] and n > EMODNET_BOX[1] and s < EMODNET_BOX[3]
            if inside and frame_hits(frame, inv_fwd, (w, s, e, n)):
                jobs.append((ix, iy, ix1, iy1))
            ix = ix1
        iy = iy1
    print(f"EMODnet: {len(jobs)} chunks", flush=True)

    def run(job):
        w, s, e, n = grid.cell_lonlat(*job)
        w, e = max(w, EMODNET_BOX[0]), min(e, EMODNET_BOX[2])
        parts = [(w, s, e, n)]
        arr = emodnet_chunk(w, s, e, n)
        if arr is None:  # refused: halve along the longer side and retry
            mid_lon, mid_lat = (w + e) / 2, (s + n) / 2
            mid_lon = round(mid_lon * EMODNET_PX / grid.k) * grid.k / EMODNET_PX
            mid_lat = round(mid_lat * EMODNET_PX / grid.k) * grid.k / EMODNET_PX
            if (e - w) >= (n - s) and w < mid_lon < e:
                parts = [(w, s, mid_lon, n), (mid_lon, s, e, n)]
            elif s < mid_lat < n:
                parts = [(w, s, e, mid_lat), (w, mid_lat, e, n)]
            else:
                return job, None
            return job, [(p, emodnet_chunk(*p)) for p in parts]
        return job, [(parts[0], arr)]

    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for job, results in ex.map(run, jobs):
            done += 1
            if results is None:
                print("  chunk failed:", job, flush=True)
                continue
            for (w, s, e, n), arr in results:
                if arr is None:
                    print("  sub-chunk failed:", (w, s, e, n), flush=True)
                    continue
                block = block_mean(arr, grid.k)
                ix0 = round((w * EMODNET_PX - grid.w0) / grid.k)
                iy_top = grid.ny - round((n * EMODNET_PX - grid.s0) / grid.k)  # array rows run north to south
                h, wd = block.shape
                dst = out[iy_top:iy_top + h, ix0:ix0 + wd]
                blk = block[:dst.shape[0], :dst.shape[1]]
                dst[...] = np.where(np.isfinite(blk), blk, dst)
            if done % 10 == 0:
                print(f"  {done}/{len(jobs)} chunks", flush=True)
    return out


def frame_hits(frame, fwd, lonlat_box) -> bool:
    w, s, e, n = lonlat_box
    k = np.linspace(0, 1, 9)
    xs = np.concatenate([w + (e - w) * k, np.full(9, e), e + (w - e) * k, np.full(9, w)])
    ys = np.concatenate([np.full(9, s), s + (n - s) * k, np.full(9, n), n + (s - n) * k])
    px, py = fwd.transform(xs, ys)
    from shapely.geometry import Polygon
    return frame.intersects(Polygon(np.column_stack([px, py])).buffer(0))


def fetch_copernicus(grid: Grid, frame, fwd, workers: int = 8) -> np.ndarray:
    out = np.full((grid.ny, grid.nx), np.nan, dtype="float32")
    n = max(1, round(1 / grid.step))
    w0, s0 = grid.w0 / EMODNET_PX, grid.s0 / EMODNET_PX
    tiles = []
    for lat in range(math.floor(s0), math.ceil(s0 + grid.ny * grid.step)):
        for lon in range(math.floor(w0), math.ceil(w0 + grid.nx * grid.step)):
            if -90 <= lat < 90 and frame_hits(frame, fwd, (lon, lat, lon + 1, lat + 1)):
                tiles.append((lat, lon))
    print(f"Copernicus GLO-90: {len(tiles)} candidate tiles", flush=True)

    def run(t):
        lat, lon = t
        name = f"Copernicus_DSM_COG_30_{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00_{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00_DEM"
        def go():
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"):
                try:
                    d = rasterio.open(f"/vsicurl/{COP90.format(n=name)}")
                except rasterio.errors.RasterioIOError as err:
                    if "404" in str(err) or "not recognized" in str(err) or "No such file" in str(err):
                        return None
                    raise
                with d:
                    return d.read(1, out_shape=(n, n), resampling=Resampling.average)
        return t, retry(go)

    found = 0
    with ThreadPoolExecutor(workers) as ex:
        for (lat, lon), arr in ex.map(run, tiles):
            if arr is None:
                continue
            found += 1
            # tiles are 1 degree and the grid step divides 1/960 degree evenly, so a tile is exactly n x n cells
            x0 = round((lon * EMODNET_PX - grid.w0) / grid.k)
            y0 = grid.ny - round(((lat + 1) * EMODNET_PX - grid.s0) / grid.k)
            ys, xs = max(0, y0), max(0, x0)
            ye, xe = min(grid.ny, y0 + n), min(grid.nx, x0 + n)
            if ye > ys and xe > xs:
                out[ys:ye, xs:xe] = arr[ys - y0:ye - y0, xs - x0:xe - x0]
    print(f"  {found} tiles found (others are all sea)", flush=True)
    return out


def fetch_etopo(grid: Grid) -> np.ndarray:
    import netCDF4
    d = netCDF4.Dataset(ETOPO)
    z, lat, lon = d.variables["z"], d.variables["lat"][:], d.variables["lon"][:]
    res = 1 / 60
    w, s = grid.w0 / EMODNET_PX, grid.s0 / EMODNET_PX
    e, n = w + grid.nx * grid.step, s + grid.ny * grid.step
    c0, c1 = max(0, int((w - lon[0]) / res)), min(len(lon), math.ceil((e - lon[0]) / res) + 1)
    r0, r1 = max(0, int((s - lat[0]) / res)), min(len(lat), math.ceil((n - lat[0]) / res) + 1)
    print(f"ETOPO 2022: rows {r0}:{r1} cols {c0}:{c1}", flush=True)
    out = np.full((grid.ny, grid.nx), np.nan, dtype="float32")
    dst_tr = grid.transform
    ratio = round(grid.step / res)
    if ratio >= 3:
        # Much coarser than ETOPO (the world map): the server is slow (about 0.5 MB/s), so sample every ratio-th cell,
        # centred in each block, instead of reading and averaging everything. The build smooths before contouring.
        off = ratio // 2
        rows, cols = np.arange(r0 + off, r1, ratio), np.arange(c0 + off, c1, ratio)
        a = np.ma.filled(z[rows[0]:rows[-1] + 1:ratio, cols[0]:cols[-1] + 1:ratio], np.nan).astype("float32")[::-1]
        src_tr = from_origin(lon[cols[0]] - grid.step / 2, lat[rows[-1]] + grid.step / 2, grid.step, grid.step)
        reproject(a, out, src_transform=src_tr, src_crs="EPSG:4326", dst_transform=dst_tr, dst_crs="EPSG:4326",
                  resampling=Resampling.nearest, src_nodata=np.nan, dst_nodata=np.nan)
        d.close()
        return out
    band = 600  # rows per request
    for r in range(r0, r1, band):
        rr = min(r + band, r1)
        a = np.ma.filled(z[r:rr, c0:c1], np.nan).astype("float32")
        src_tr = from_origin(lon[c0] - res / 2, lat[rr - 1] + res / 2, res, res)
        a = a[::-1]  # file runs south to north
        tmp = np.full((grid.ny, grid.nx), np.nan, dtype="float32")
        reproject(a, tmp, src_transform=src_tr, src_crs="EPSG:4326", dst_transform=dst_tr, dst_crs="EPSG:4326",
                  resampling=Resampling.average if grid.step >= res else Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
        out = np.where(np.isfinite(tmp), tmp, out)
    d.close()
    return out


def main(region: str, use_emodnet: bool = True) -> None:
    a = AREAS[region]
    f = a["fetch"]
    out_dir = Path("data/raw") / region
    out_dir.mkdir(parents=True, exist_ok=True)
    grid = Grid(a["box"], f["step_deg"])
    print(f"{region}: grid {grid.nx} x {grid.ny} cells of {grid.step:.5f} deg ({grid.nx * grid.ny / 1e6:.1f} M)", flush=True)
    world = a["extent"] and a["extent"][2] - a["extent"][0] > 3e7
    frame = box(*a["extent"]).buffer(grid.step * 111_000 * 2) if not world else box(-1e9, -1e9, 1e9, 1e9)
    fwd = Transformer.from_crs("EPSG:4326", a["crs"], always_xy=True)
    t0 = time.time()
    src = {}
    etopo = fetch_etopo(grid)
    src["etopo"] = float(np.isfinite(etopo).mean())
    em = cop = None
    if "emodnet" in f.get("sea", []) and use_emodnet:
        em = fetch_emodnet(grid, frame, fwd)
        src["emodnet"] = float(np.isfinite(em).mean())
    if "copernicus" in f.get("land", []):
        cop = fetch_copernicus(grid, frame, fwd)
        src["copernicus"] = float(np.isfinite(cop).mean())
    z = etopo.copy()
    if em is not None:
        z = np.where(np.isfinite(em), np.minimum(em, 0.0), z)
    if cop is not None:
        z = np.where(np.isfinite(cop) & (cop > 0.5), cop, z)
    profile = {"driver": "GTiff", "dtype": "float32", "count": 1, "width": grid.nx, "height": grid.ny, "crs": "EPSG:4326",
               "transform": grid.transform, "nodata": np.nan, "compress": "deflate", "predictor": 3, "tiled": True}
    with rasterio.open(out_dir / "merged.tif", "w", **profile) as dst:
        dst.write(z.astype("float32"), 1)
    (out_dir / "merged.json").write_text(json.dumps({"region": region, "step_deg": grid.step, "cells": [grid.nx, grid.ny],
                                                     "share_with_data": {k: round(v, 4) for k, v in src.items()},
                                                     "seconds": round(time.time() - t0)}, indent=1))
    print(f"-> {out_dir / 'merged.tif'} ({(out_dir / 'merged.tif').stat().st_size / 1e6:.1f} MB, {time.time() - t0:.0f} s)  sources {src}")


if __name__ == "__main__":
    main(sys.argv[1], "--no-emodnet" not in sys.argv)
