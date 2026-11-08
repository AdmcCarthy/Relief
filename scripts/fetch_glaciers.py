"""Fetch glacier outlines for an area box from the GLIMS WFS (Randolph Glacier Inventory 6.0, CC BY 4.0).

RGI 6.0 outlines for Scandinavia come from NVE's inventory (around 1999-2006). They are the observed
'permanent ice' layer: Norway has no mapped permanent snow line; seasonal snow varies year to year.

Usage: python scripts/fetch_glaciers.py <area>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests
from areas import AREAS

WFS = "https://www.glims.org/geoserver/ows"


def main(area: str) -> None:
    w, s, e, n = AREAS[area]["box"]
    params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": "GLIMS:RGI_Scandinavia",
              "outputFormat": "application/json", "srsName": "EPSG:4326", "bbox": f"{s},{w},{n},{e},urn:ogc:def:crs:EPSG::4326"}
    r = requests.get(WFS, params=params, timeout=300)
    r.raise_for_status()
    fc = r.json()
    out = Path("data/raw") / area / "glaciers_rgi6.geojson"
    out.write_text(json.dumps(fc))
    area_km2 = sum(f["properties"].get("AREA", 0) for f in fc["features"])
    print(f"RGI 6.0: {len(fc['features'])} glaciers, {area_km2:.0f} km² -> {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "vestland")
