"""Combine sea-floor sources into one surface, best source first, with feathered seams and a source map.

Priority (finest first): Kartverket 50 m (Norwegian waters, CC BY 4.0) > Denmark's Depth Model 50 m (Danish
EEZ; free, needs a Dataforsyningen account: place GeoTIFFs in data/raw/<area>/denmark_dybdemodel50/) >
EMODnet DTM 2024 (~115 m, European seas) > GEBCO_2026 (~450 m, global; optional GeoTIFF subset in
data/raw/<area>/gebco/). Each finer source is blended in over FEATHER_M at its edge so seams do not show as
steps in shading. Returns depths (negative, metres), a source index per cell and overlap statistics.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.warp import reproject
from scipy.ndimage import distance_transform_edt

SOURCES = ["gebco", "emodnet", "denmark", "kartverket"]  # coarse -> fine; index stored in the source map
FEATHER_M = 1500


def _warp(arr, src_tr, src_crs, dst_tr, w, h, crs):
    out = np.full((h, w), np.nan, dtype="float32")
    reproject(arr, out, src_transform=src_tr, src_crs=src_crs, dst_transform=dst_tr, dst_crs=crs,
              resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    return out


def _mosaic(files, nodata=None):
    srcs = [rasterio.open(f) for f in files]
    crs = srcs[0].crs
    arr, tr = merge(srcs, nodata=nodata if nodata is not None else srcs[0].nodata)
    nd = nodata if nodata is not None else srcs[0].nodata
    for s in srcs:
        s.close()
    a = arr[0].astype("float32")
    if nd is not None:
        a[np.isclose(a, nd)] = np.nan
    a[np.abs(a) > 2e4] = np.nan
    return a, tr, crs


def layers(raw: Path, tr, w, h, crs) -> dict[str, np.ndarray]:
    out = {}
    g = sorted((raw / "gebco").glob("*.tif"))
    if g:
        a, t, c = _mosaic(g)
        out["gebco"] = _warp(a, t, c, tr, w, h, crs)
    if (raw / "emodnet_dtm.tif").exists():
        with rasterio.open(raw / "emodnet_dtm.tif") as s:
            out["emodnet"] = _warp(s.read(1).astype("float32"), s.transform, s.crs, tr, w, h, crs)
    d = sorted((raw / "denmark_dybdemodel50").glob("*.tif"))
    if d:
        a, t, c = _mosaic(d)
        out["denmark"] = _warp(-np.abs(a), t, c, tr, w, h, crs)  # model stores depth as positive or negative
    k = sorted((raw / "kartverket_sea50").glob("NHS-D*.tif"))
    if k:
        a, t, c = _mosaic(k, nodata=99999.0)
        out["kartverket"] = _warp(a, t, c, tr, w, h, crs)
    return out


def combine(raw: Path, tr, w, h, crs, cell: float):
    L = layers(raw, tr, w, h, crs)
    z = np.full((h, w), np.nan, dtype="float32")
    src = np.zeros((h, w), dtype="uint8")
    stats = {}
    for i, name in enumerate(SOURCES):
        if name not in L:
            continue
        a = L[name]
        ok = np.isfinite(a) & (a < 0)
        if not ok.any():
            continue
        both = ok & np.isfinite(z)
        if both.sum() > 100:
            d = a[both] - z[both]
            stats[name] = {"overlap_cells": int(both.sum()), "median_diff_m": round(float(np.median(d)), 1),
                           "p90_abs_diff_m": round(float(np.percentile(np.abs(d), 90)), 1)}
        # feather: weight rises from 0 at the source's edge to 1 at FEATHER_M inside it
        wgt = np.clip(distance_transform_edt(ok) * cell / FEATHER_M, 0, 1).astype("float32")
        wgt[~ok] = 0
        wgt = np.where(np.isfinite(z), wgt, ok.astype("float32"))  # nothing beneath: no feathering
        base = np.where(np.isfinite(z), z, a)
        z = np.where(ok, base * (1 - wgt) + a * wgt, z)
        src[ok & (wgt > 0.5)] = i
    cover = {SOURCES[i]: round(float((src == i)[np.isfinite(z)].mean()), 3) for i in range(len(SOURCES)) if SOURCES[i] in L}
    return z, src, {"available": [n for n in SOURCES if n in L], "share_of_sea": cover, "overlap": stats}
