"""The source plan is consistent, the build script plans without touching the network, its blending behaves, and the
example assets match the regions and the page budgets."""

import json
import math
from pathlib import Path

import build_hires as bh
import numpy as np
import pytest
import render_region as rr

from regions import load

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "regions" / "sources.json").read_text())
REGIONS = {r["id"]: r for r in load()["regions"]}
ADAPTERS = {"cog_tiles", "cog_vrt", "wcs_chunks", "opendap", "geonorge_download", "http_zip", "wcs", "manual"}
STATUSES = {"verified", "documented", "unverified", "manual"}


def test_every_region_has_a_plan_and_every_source_is_defined():
    assert set(PLAN["regions"]) == set(REGIONS)
    for rid, spec in PLAN["regions"].items():
        for kind in ("land", "sea"):
            assert spec[kind], f"{rid} has no {kind} sources"
            for sid in spec[kind]:
                assert sid in PLAN["sources"], f"{rid}: unknown source {sid}"


def test_sources_are_described_honestly():
    for sid, s in PLAN["sources"].items():
        assert s["adapter"] in ADAPTERS, sid
        assert s["status"] in STATUSES, sid
        assert s["licence"] and s["attribution"], f"{sid}: record licence and attribution"
        assert len(s["bbox"]) == 4 and s["bbox"][0] < s["bbox"][2] and s["bbox"][1] < s["bbox"][3], sid
        if s["adapter"] == "manual":
            assert s["status"] in {"manual", "verified", "unverified"}, sid


def test_style_is_the_fixed_house_style():
    st = PLAN["style"]
    assert st["name"] == "Detuned"
    assert "stepped" in st["relief"] and "linear" in st["bathymetry"]
    assert st["contours"] is False and st["coastline"] is False


@pytest.mark.parametrize("rid", PLAN["regions"])
def test_every_list_ends_in_a_source_that_covers_the_region(rid):
    """The last source of each list is the fallback: it must cover the whole region so no cell is empty."""
    box = REGIONS[rid]["bbox"]
    for kind in ("land", "sea"):
        last = PLAN["sources"][PLAN["regions"][rid][kind][-1]]
        w, s, e, n = last["bbox"]
        assert w <= box[0] and s <= box[1] and e >= box[2] and n >= box[3], f"{rid} {kind} fallback {last['name']} does not cover it"


@pytest.mark.parametrize("rid", PLAN["regions"])
def test_web_cells_respect_the_texture_and_size_budget(rid):
    spec = PLAN["regions"][rid]["web_cell_m"]
    x0, y0, x1, y1 = REGIONS[rid]["extent"]
    assert spec["hires"] <= spec["now"]
    for cell in spec.values():
        w, h = math.ceil((x1 - x0) / cell), math.ceil((y1 - y0) / cell)
        assert max(w, h) <= PLAN["limits"]["texture_px"], f"{rid} at {cell} m is {max(w, h)} px"
    w, h = math.ceil((x1 - x0) / spec["hires"]), math.ceil((y1 - y0) / spec["hires"])
    assert w * h * 0.9 / 1e6 <= PLAN["limits"]["web_budget_mb_per_region"] * 1.3, "estimated WebP over budget"


@pytest.mark.parametrize("rid", PLAN["regions"])
def test_plan_needs_no_network_and_skips_what_cannot_run(rid):
    steps = bh.make_plan(rid)
    assert steps
    for st in steps:
        if st["adapter"] == "manual":
            assert not st["runnable"] or (bh.manual_dir(rid, st["id"]).exists())
        if st["runnable"]:
            assert st["adapter"] in bh.ADAPTERS or st["adapter"] == "manual"
    skipped_far = bh.make_plan("north_sea")
    assert any(s["id"] == "npi_svalbard_dtm20" for s in bh.make_plan("barents_sea") if s["runnable"])
    assert not any(s["id"] == "npi_svalbard_dtm20" and s["runnable"] for s in skipped_far)  # Svalbard is not in the North Sea


def test_unverified_sources_need_a_flag():
    assert not next(s for s in bh.make_plan("north_sea") if s["id"] == "dk_dybdemodel_50")["runnable"]
    only = {s["id"] for s in bh.make_plan("north_sea", only={"cop_glo30"}) if s["runnable"]}
    assert only == {"cop_glo30"}


def test_blend_prefers_the_finer_layer_and_feathers_the_seam():
    h = w = 120
    coarse = np.full((h, w), -100.0, dtype="float32")
    fine = np.full((h, w), np.nan, dtype="float32")
    fine[:, 60:] = -120.0  # the finer source covers the right half, 20 m deeper
    z, idx, stats = bh.blend([("coarse", coarse), ("fine", fine)], cell=500, valid=lambda a: a < 0)
    assert z[60, 5] == -100 and z[60, 115] == -120  # each source where only it exists / far inside the fine one
    assert idx[60, 5] == 1 and idx[60, 115] == 2
    seam = z[60, 58:75]
    assert np.all(np.diff(seam) <= 1e-4), "the seam must ramp monotonically, not step"
    assert stats["fine"]["median_diff_m"] == -20.0


def test_blend_ignores_cells_a_source_may_not_contribute():
    base = np.full((20, 20), -50.0, dtype="float32")
    land_like = np.full((20, 20), 30.0, dtype="float32")
    z, idx, _ = bh.blend([("base", base), ("land", land_like)], cell=500, valid=lambda a: a < 0)
    assert np.all(z == -50) and np.all(idx == 1)


def test_land_sea_combine_has_a_clean_coast():
    land = np.array([[10.0, 0.0, 0.2, np.nan]], dtype="float32")
    sea = np.array([[-5.0, -20.0, -0.3, np.nan]], dtype="float32")
    z = bh.combine_land_sea(land, sea)
    assert z[0, 0] == 10 and z[0, 1] == -20 and z[0, 2] == -1 and z[0, 3] == -1  # sea at least 1 m deep


def test_elevation_encoding_round_trips_within_a_step():
    z = np.array([[-10452.3, -4000.0, -0.4, 0.0, 12.26, 8848.0]], dtype="float32")
    back = rr.decode(rr.encode(z))
    assert np.max(np.abs(back - z)) <= rr.STEP / 2 + 1e-6
    assert rr.BASE <= z.min() and z.max() < rr.BASE + 65535 * rr.STEP


@pytest.mark.parametrize("rid", [r for r in REGIONS if (ROOT / "data" / "out" / r / "demo" / "meta.json").exists()])
def test_built_assets_match_the_region_and_budget(rid):
    d = ROOT / "data" / "out" / rid / "demo"
    meta = json.loads((d / "meta.json").read_text())
    assert meta["bounds"] == REGIONS[rid]["extent"] or rid == "vestland"
    blob = (d / "elev.webp").read_bytes()
    z = rr.decode(blob) if rid != "vestland" else None
    assert len(blob) / 1e6 <= PLAN["limits"]["web_budget_mb_per_region"]
    assert max(meta["size"]) <= PLAN["limits"]["texture_px"]
    if z is not None:
        assert z.shape == (meta["size"][1], meta["size"][0])
        assert abs(float(z.min()) - meta["zmin"]) <= rr.STEP and abs(float(z.max()) - meta["zmax"]) <= rr.STEP
        assert (z > 0).any() and (z < 0).any()
        assert sum(meta["zones"]["share_of_land"].values()) == pytest.approx(1.0, abs=0.02)
    assert (d / "zones.png").exists()
