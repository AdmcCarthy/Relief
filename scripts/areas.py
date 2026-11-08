"""Named areas for the pipeline, read from the shared region registry (regions/regions.json).

AREAS[id] gives: box (lon/lat bounds to fetch), crs (anything pyproj accepts), extent (projected frame,
metres), lods (cell sizes per level of detail) and fetch (resolution and sources). Add or change a region
in regions/regions.json, then run `python scripts/regions.py sync`.
"""

import json
from pathlib import Path

_REG = json.loads((Path(__file__).resolve().parents[1] / "regions" / "regions.json").read_text())

AREAS = {
    r["id"]: {"box": tuple(r.get("bbox", ())), "crs": r["crs"]["code"], "extent": r.get("extent"),
              "lods": r.get("lods", {}), "fetch": r.get("fetch", {}), "name": r["name"]}
    for r in _REG["regions"]
}
