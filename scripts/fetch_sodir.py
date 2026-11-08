"""Fetch Sodir (Norwegian Offshore Directorate) block and field outlines, used to check region coverage.

Layers on the Sodir FactMaps service (open data, NLOD): 802 Blocks, 502 Fields by status. Saved to
data/raw/regions/ (not committed); `scripts/regions.py check` reads them.

Usage: python scripts/fetch_sodir.py
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

SERVICE = "https://factmaps.sodir.no/api/rest/services/Factmaps/FactMapsWGS84/FeatureServer"
LAYERS = {"sodir_blocks": 802, "sodir_fields": 502}


def pull(layer: int) -> list[dict]:
    feats, offset = [], 0
    while True:
        r = requests.get(f"{SERVICE}/{layer}/query", timeout=120, params={
            "where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson",
            "resultOffset": offset, "resultRecordCount": 1000})
        r.raise_for_status()
        batch = r.json().get("features", [])
        feats += batch
        if len(batch) < 1000:
            return feats
        offset += 1000


def main() -> None:
    out = Path("data/raw/regions")
    out.mkdir(parents=True, exist_ok=True)
    for name, layer in LAYERS.items():
        feats = pull(layer)
        (out / f"{name}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
        print(f"{name}: {len(feats)} features")


if __name__ == "__main__":
    main()
