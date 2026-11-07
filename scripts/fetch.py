"""Fetch open elevation data for an area box.

Sea floor: EMODnet Bathymetry DTM (European seas, 1/16 arc-minute, about 115 m), cut to the box through
its WCS service. Land: Copernicus DEM GLO-90 (90 m, 1-degree Cloud Optimized GeoTIFF tiles on the open
AWS bucket). Both are open: see docs/sources.md for licences and attribution.

Usage: python scripts/fetch.py <area>      (areas in scripts/areas.py)
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import requests
from areas import AREAS

EMODNET_WCS = "https://ows.emodnet-bathymetry.eu/wcs"
COP90 = "https://copernicus-dem-90m.s3.amazonaws.com/{n}/{n}.tif"


def get(url: str, **kw) -> requests.Response:
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=600, **kw)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def fetch_emodnet(box: tuple[float, float, float, float], out: Path) -> Path:
    w, s, e, n = box
    params = [("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"), ("coverageId", "emodnet__mean"),
              ("subset", f"Lat({s},{n})"), ("subset", f"Long({w},{e})"), ("format", "image/tiff")]
    r = get(EMODNET_WCS, params=params)
    if not r.content.startswith((b"II*\x00", b"MM\x00*")):
        raise RuntimeError(f"EMODnet WCS did not return a GeoTIFF: {r.text[:300]}")
    p = out / "emodnet_dtm.tif"
    p.write_bytes(r.content)
    return p


def fetch_copernicus(box: tuple[float, float, float, float], out: Path) -> list[Path]:
    w, s, e, n = box
    paths = []
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            name = f"Copernicus_DSM_COG_30_{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00_{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00_DEM"
            p = out / f"{name}.tif"
            if not p.exists():
                r = get(COP90.format(n=name))
                if r.status_code == 404:  # all-sea tiles do not exist
                    continue
                p.write_bytes(r.content)
            paths.append(p)
    return paths


def main(area: str) -> None:
    a = AREAS[area]
    out = Path("data/raw") / area
    out.mkdir(parents=True, exist_ok=True)
    e = fetch_emodnet(a["box"], out)
    print(f"EMODnet: {e} ({e.stat().st_size / 1e6:.1f} MB)")
    c = fetch_copernicus(a["box"], out)
    print(f"Copernicus GLO-90: {len(c)} tiles ({sum(p.stat().st_size for p in c) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "vestland")
