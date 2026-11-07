"""Quality checks on built relief layers."""

import itertools
import json
from pathlib import Path

import pytest
from shapely.geometry import shape

OUT = Path(__file__).resolve().parents[1] / "data" / "out" / "vestland"
BUDGET_MB = {"overview": 0.3, "regional": 1.5, "detail": 4.0}


@pytest.fixture(scope="module")
def manifest():
    return json.loads((OUT / "manifest.json").read_text())


def layers(lod):
    return json.loads((OUT / f"{lod}.geojson").read_text())["features"]


@pytest.mark.parametrize("lod", list(BUDGET_MB))
def test_stacked_layers_nest(lod):
    for kind in ("land", "sea"):
        geoms = [shape(f["geometry"]) for f in layers(lod) if f["properties"]["kind"] == kind]
        areas = [g.area for g in geoms]
        assert areas == sorted(areas, reverse=True), f"{kind} levels must shrink as they go higher/deeper"
        for lo, hi in itertools.pairwise(geoms):
            if not hi.is_empty:  # a higher level lies (almost) inside the lower one
                assert hi.difference(lo.buffer(50)).area < 0.01 * hi.area


@pytest.mark.parametrize("lod", list(BUDGET_MB))
def test_size_budget(lod, manifest):
    assert manifest["lods"][lod]["bytes"] / 1e6 <= BUDGET_MB[lod]


def test_generalisation_by_scale(manifest):
    L = manifest["lods"]
    assert L["overview"]["coast_parts"] < L["regional"]["coast_parts"] < L["detail"]["coast_parts"]
    for lod in L.values():
        assert lod["coast_parts"] <= lod["coast_parts_ungeneralised"]


def test_land_and_sea_fill_the_frame(manifest):
    feats = layers("regional")
    land0 = shape(next(f for f in feats if f["properties"]["kind"] == "land" and f["properties"]["level"] == 0)["geometry"])
    x0, y0, x1, y1 = manifest["lods"]["regional"]["bounds"]
    frame = (x1 - x0) * (y1 - y0)
    assert 0.3 < land0.area / frame < 0.8  # Vestland box: about half land
