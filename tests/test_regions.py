"""The region registry is consistent, covers what it claims to, and built regions meet the same quality checks."""

import itertools
import json
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import shape

from regions import REG, crs_of, derive_extent, load, outline

ROOT = Path(__file__).resolve().parents[1]
REGIONS = {r["id"]: r for r in load()["regions"]}
COVERAGE = json.loads((REG / "coverage.json").read_text())
BUILT = [rid for rid in REGIONS if (ROOT / "data" / "out" / rid / "manifest.json").exists()]
BUDGET_MB = {"overview": 0.6, "regional": 2.5, "detail": 5.0}
BUDGET_OVERRIDE = {"world": {"overview": 1.5, "regional": 4.0}}  # whole-world coastlines are long


def test_expected_regions_exist():
    assert {"north_sea", "norwegian_sea", "barents_sea", "ne_europe", "world"} <= set(REGIONS)


@pytest.mark.parametrize("rid", REGIONS)
def test_derived_fields_are_current(rid):
    """extent/bbox in regions.json must match the design: run `python scripts/regions.py sync` after editing."""
    r = REGIONS[rid]
    assert [round(v) for v in derive_extent(r)] == r["extent"]
    assert r["crs"]["proj4"], "proj4 string missing"
    x0, y0, x1, y1 = r["extent"]
    assert x1 > x0 and y1 > y0
    w, s, e, n = r["bbox"]
    assert -180 <= w < e <= 180 and -90 <= s < n <= 90
    inv = Transformer.from_crs(crs_of(r), "EPSG:4326", always_xy=True)
    for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
        lon, lat = inv.transform(x, y)
        if not r["design"].get("world"):
            assert w - 0.05 <= lon <= e + 0.05 and s - 0.05 <= lat <= n + 0.05, "bbox must contain the extent corners"
    assert outline(r).is_valid


def test_outlines_file_matches_registry():
    fc = json.loads((REG / "regions.geojson").read_text())
    assert [f["properties"]["id"] for f in fc["features"]] == list(REGIONS)


def test_barents_has_norway_at_the_bottom():
    """In the polar projection the central meridian runs straight down: Finnmark (25 E) lies below Svalbard (20 E)."""
    r = REGIONS["barents_sea"]
    t = Transformer.from_crs("EPSG:4326", crs_of(r), always_xy=True)
    _, y_norway = t.transform(25.8, 71.2)
    _, y_svalbard = t.transform(20.0, 78.0)
    assert y_norway < y_svalbard
    x_norway, _ = t.transform(30.0, 70.0)
    x_svalbard, _ = t.transform(30.0, 80.0)
    assert abs(x_norway - x_svalbard) < 1  # the 30 E meridian is a vertical line


def test_coverage_report_meets_each_regions_spec():
    for rid, r in REGIONS.items():
        for key, spec in r.get("coverage", {}).items():
            groups = COVERAGE[rid][key]
            if key == "wells":
                for country, s in groups.items():
                    assert s["share_inside"] >= spec["min_inside"], f"{rid}: {country} wells"
                continue
            for a in spec["include"]:
                assert groups[a.lower()]["share_area_inside"] >= spec["min_area_inside"], f"{rid}: {key} {a}"
            for a in spec.get("exclude", []):
                assert groups[a.lower()]["share_area_inside"] <= spec["max_excluded_area_inside"], f"{rid}: {key} {a} leaks in"


def test_ne_europe_has_no_norwegian_sea_fields_and_all_north_sea_ones():
    f = COVERAGE["ne_europe"]["sodir_fields"]
    assert f["norwegian sea"]["touching"] == 0 and f["north sea"]["inside"] == f["north sea"]["total"]


@pytest.mark.parametrize("rid", BUILT)
def test_built_region_matches_registry_and_nests(rid):
    out = ROOT / "data" / "out" / rid
    m = json.loads((out / "manifest.json").read_text())
    assert m["lods"].keys() == REGIONS[rid]["lods"].keys()
    for lod, cfg in m["lods"].items():
        assert cfg["cell"] == REGIONS[rid]["lods"][lod]["cell"]
        assert cfg["bytes"] / 1e6 <= BUDGET_OVERRIDE.get(rid, BUDGET_MB)[lod], f"{rid} {lod} over its size budget"
        feats = json.loads((out / f"{lod}.geojson").read_text())["features"]
        for kind in ("land", "sea"):
            geoms = [shape(f["geometry"]) for f in feats if f["properties"]["kind"] == kind]
            areas = [g.area for g in geoms]
            assert areas == sorted(areas, reverse=True)
            for lo, hi in itertools.pairwise(geoms):
                if not hi.is_empty:
                    assert hi.difference(lo.buffer(cfg["cell"] / 4 + 50)).area < 0.01 * hi.area
    parts = [m["lods"][k]["coast_parts"] for k in m["lods"]]
    assert parts == sorted(parts), "coarser levels of detail keep fewer coastline pieces"
