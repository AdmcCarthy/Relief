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
ADAPTERS = {"cog_tiles", "cog_vrt", "wcs_chunks", "opendap", "geonorge_download", "http_zip", "wcs", "zip_clip", "remote_tiles", "manual"}
STATUSES = {"verified", "documented", "unverified", "manual", "restricted"}


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


def test_warp_pieces_matches_a_full_grid_warp(tmp_path):
    """Windowed warping of small pieces covers the same cells as warping each into the whole region, to within a metre
    (smooth terrain: on pure noise the two differ at piece edges, which is GDAL's interpolation, not an error)."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import reproject

    crs, cell = "EPSG:25833", 1000.0
    tr, w, h = rasterio.Affine(cell, 0, 200_000, 0, -cell, 6_700_000), 120, 100
    yy, xx = np.mgrid[0:80, 0:40]
    z = (100 + 2 * yy + 3 * xx).astype("float32")
    files = []
    for i, (lon, lat) in enumerate([(11.0, 60.5), (11.4, 60.7), (12.3, 61.1)]):  # overlapping 0.6 degree pieces
        path = tmp_path / f"p{i}.tif"
        bh.save_tif(path, z, from_origin(lon, lat, 0.6 / 40, 0.5 / 80), "EPSG:4326")
        files.append(path)
    got = bh.warp_pieces(files, tr, w, h, crs, cell)
    want = np.full((h, w), np.nan, dtype="float32")
    for f in files:
        tmp = np.full((h, w), np.nan, dtype="float32")
        with rasterio.open(f) as d:
            reproject(rasterio.band(d, 1), tmp, dst_transform=tr, dst_crs=crs, dst_nodata=np.nan, tolerance=0.0,
                      resampling=Resampling.average if cell >= abs(d.res[0]) * 111_320 else Resampling.bilinear)
        want = np.where(np.isfinite(want), want, tmp)
    assert np.isfinite(got).sum() > 500
    assert np.array_equal(np.isfinite(got), np.isfinite(want))
    both = np.isfinite(got)
    assert np.max(np.abs(got[both] - want[both])) < 1.0


def test_a_coarser_source_never_outranks_a_finer_one_it_would_overwrite():
    """EMODnet (115 m) must come before IBCAO (400 m) and the global grids; the national 25 and 50 m models come first."""
    for rid, spec in PLAN["regions"].items():
        sea = spec["sea"]
        res = [PLAN["sources"][s]["res_m"] for s in sea]
        for name in ("ibcao_v5", "gebco_2026", "etopo_2022_60s"):
            if name in sea and "emodnet_dtm_2024" in sea:
                assert sea.index("emodnet_dtm_2024") < sea.index(name), f"{rid}: {name} would overwrite EMODnet"
        assert res == sorted(res) or sea[0].startswith(("kartverket", "dk_", "bsh_")), f"{rid}: sea list is not finest first"


def test_services_that_fill_with_zero_are_masked():
    assert PLAN["sources"]["kartverket_dtm_seamless"]["zero_is_nodata"] is True


def test_os_grid_references_give_the_right_squares():
    assert bh.os_grid_square("hp40") == (440_000, 1_200_000, 450_000, 1_210_000)  # Shetland, Unst
    assert bh.os_grid_square("NT34") == (330_000, 640_000, 340_000, 650_000)  # near Edinburgh
    assert bh.os_grid_square("TQ38")[:2] == (530_000, 180_000)  # central London
    assert bh.os_grid_square("SV00")[:2] == (0, 0)  # the grid origin, south-west of Scilly
    assert bh.os_grid_square("SW00")[:2] == (100_000, 0)
    assert bh.os_grid_square("xx") is None


def test_nothing_that_cannot_be_redistributed_is_in_a_region_plan():
    """Products are published, so every planned source needs an open licence on record. Restricted ones are excluded."""
    restricted = {sid for sid, s in PLAN["sources"].items() if s.get("redistributable") is False}
    assert "kartverket_dtm_seamless" in restricted  # Norge digitalt licence
    for rid, spec in PLAN["regions"].items():
        for sid in spec["land"] + spec["sea"]:
            assert sid not in restricted, f"{rid} plans {sid}, which cannot be redistributed"
            assert PLAN["sources"][sid]["licence"], sid


def test_gebco_tiles_are_listed_completely():
    tiles = PLAN["sources"]["gebco_2026"]["tiles"]
    assert len(tiles) == 8
    boxes = {tuple(t["bbox"]) for t in tiles}
    assert boxes == {(w, s, w + 90, s + 90) for w in (-180, -90, 0, 90) for s in (-90, 0)}
    for t in tiles:
        w, s, e, n = t["bbox"]
        assert t["url"].endswith(f"gebco_2026_n{float(n)}_s{float(s)}_w{float(w)}_e{float(e)}_geotiff.tif")


def test_read_band_block_averages_a_window(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    z = np.arange(48 * 40, dtype="float32").reshape(48, 40)
    path = tmp_path / "b.tif"
    bh.save_tif(path, z, from_origin(0, 10, 0.1, 0.1), "EPSG:4326")
    with rasterio.open(path) as d:
        got = bh.read_band(d, 8, 40, 4, 36, 4)
    want = z[8:40, 4:36].reshape(8, 4, 8, 4).mean(axis=(1, 3))
    assert got.shape == (8, 8) and np.allclose(got, want)


def test_first_layer_needs_no_feathering_and_a_covering_finer_layer_replaces_it():
    coarse = np.full((30, 30), -100.0, dtype="float32")
    fine = np.full((30, 30), -140.0, dtype="float32")
    z, idx, _ = bh.blend([("coarse", coarse)], cell=500, valid=lambda a: a < 0)
    assert np.all(z == -100) and np.all(idx == 1)
    z, idx, stats = bh.blend([("coarse", coarse), ("fine", fine)], cell=500, valid=lambda a: a < 0)
    assert z[15, 15] == -140 and "fine" in stats  # the interior is entirely the finer layer
    assert -140 < z[0, 0] < -100  # the grid edge counts as a boundary: the finer layer is feathered in over the first cells
