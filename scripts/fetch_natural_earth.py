"""Natural Earth 10 m countries and populated places (public domain) for the slide map's outline and cities.

    python scripts/fetch_natural_earth.py        # -> data/raw/natural_earth/*.geojson and provenance.json (skips files present)

Attribution wherever they are drawn: "Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com".
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "natural_earth"
BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
FILES = ["ne_10m_admin_0_countries", "ne_10m_populated_places_simple"]
ATTRIBUTION = "Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com"


def ensure() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        p = OUT / f"{name}.geojson"
        if p.exists():
            continue
        r = requests.get(BASE + f"{name}.geojson", timeout=120)
        r.raise_for_status()
        p.write_bytes(r.content)
    prov = OUT / "provenance.json"
    if not prov.exists():
        prov.write_text(json.dumps({
            "source": "Natural Earth 1:10m cultural vectors, GeoJSON build from github.com/nvkelso/natural-earth-vector (master)",
            "licence": "public domain", "attribution": ATTRIBUTION, "fetched": date.today().isoformat(),
            "files": {n + ".geojson": (OUT / f"{n}.geojson").stat().st_size for n in FILES},
        }, indent=1), encoding="utf-8")
    return OUT


if __name__ == "__main__":
    d = ensure()
    print(d, [p.name for p in d.iterdir()])
