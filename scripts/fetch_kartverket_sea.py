"""Fetch Kartverket's 50 m sea-floor terrain model (CC BY 4.0) for an area box, via the Geonorge download API.

Delivered in geographic cells of 0.5 deg latitude x 0.5 deg longitude, clipped to where there are data, as
GeoTIFFs at 50 m in UTM 33 (EPSG:25833). Cell NHS-Drrcc covers latitude 55 + rr/2 to 55.5 + rr/2 and longitude
cc/2 to cc/2 + 0.5 (scheme fitted from delivered files, checked on every download).

Usage: python scripts/fetch_kartverket_sea.py <area>
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import rasterio
import requests
from areas import AREAS
from pyproj import Transformer

UUID = "67a3a191-49cc-45bc-baf0-eaaf7c513549"  # Dybdedata terrengmodeller 50 meters grid
API = "https://nedlasting.geonorge.no/api"


def cells_for(box) -> list[str]:
    w, s, e, n = box
    r0, r1 = int((s - 55) // 0.5), int((n - 55 - 1e-9) // 0.5)
    c0, c1 = int(w // 0.5), int((e - 1e-9) // 0.5)
    return [f"NHS-D{r:02d}{c:02d}" for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]


def main(area: str) -> None:
    out = Path("data/raw") / area / "kartverket_sea50"
    out.mkdir(parents=True, exist_ok=True)
    available = {a["code"] for a in requests.get(f"{API}/codelists/area/{UUID}", timeout=60).json()}
    want = [c for c in cells_for(AREAS[area]["box"]) if c in available]
    todo = [c for c in want if not (out / f"{c}_50M_E25833.tif").exists()]
    if todo:
        order = {"orderLines": [{"metadataUuid": UUID, "areas": [{"code": c, "type": "celle", "name": c} for c in todo],
                                  "projections": [{"code": "25833"}], "formats": [{"name": "TIFF"}]}]}
        r = requests.post(f"{API}/order", json=order, timeout=120)
        r.raise_for_status()
        for f in r.json()["files"]:
            z = zipfile.ZipFile(io.BytesIO(requests.get(f["downloadUrl"], timeout=300).content))
            z.extractall(out)
    t = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True)
    bad = []
    for c in want:
        with rasterio.open(out / f"{c}_50M_E25833.tif") as src:
            b = src.bounds
            lon, lat = t.transform((b.left + b.right) / 2, (b.bottom + b.top) / 2)
            r_, c_ = int(c[5:7]), int(c[7:9])
            if not (55 + r_ / 2 - 0.05 <= lat <= 55.5 + r_ / 2 + 0.05 and c_ / 2 - 0.1 <= lon <= c_ / 2 + 0.6):
                bad.append(c)
    for f in out.glob("NHS-D*.tif"):  # remove cells from earlier runs that are outside the area
        if f.name[:9] not in want:
            f.unlink()
    (out / "cells.json").write_text(json.dumps({"cells": want, "grid_mismatch": bad}))
    print(f"Kartverket sea 50 m: {len(want)} cells ({len(todo)} downloaded); grid mismatches: {bad or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "vestland")
