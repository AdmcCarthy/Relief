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


DEMO = OUT / "demo"


def test_demo_assets_decode_and_fit_budget():
    import numpy as np
    from PIL import Image

    meta = json.loads((DEMO / "meta.json").read_text())
    e = np.array(Image.open(DEMO / "elev.webp")).astype(int)
    z = meta["encoding"]["base"] + (e[..., 0] * 256 + e[..., 1]) * meta["encoding"]["step"]
    assert e.shape[:2] == (meta["size"][1], meta["size"][0])
    assert z.max() > 1500 and z.min() < -1000  # Hardangervidda and the Sognefjord deeps
    assert (DEMO / "elev.webp").stat().st_size < 1.5e6
    ice = np.array(Image.open(DEMO / "glacier.png"))
    share = (ice > 127).mean()
    assert 0.001 < share < 0.02  # Folgefonna, Hardangerjøkulen and smaller glaciers
    assert np.median(z[ice > 127]) > 1000  # glaciers sit high


def test_kartverket_50m_adds_detail_over_gebco_scale():
    import numpy as np
    from PIL import Image

    meta = json.loads((DEMO / "meta.json").read_text())

    def z(name):
        e = np.array(Image.open(DEMO / "compare" / f"{name}.webp")).astype(int)
        return meta["encoding"]["base"] + (e[..., 0] * 256 + e[..., 1]) * meta["encoding"]["step"]

    rough = {k: np.abs(np.diff(z(k), axis=1))[z(k)[:, 1:] < 0].mean() for k in ("gebco450", "emodnet115", "kartverket50")}
    assert rough["gebco450"] < rough["emodnet115"] <= rough["kartverket50"] * 1.05
