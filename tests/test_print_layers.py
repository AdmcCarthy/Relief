"""print_layers: scale rules, hillshade model, contour generalisation and a real run on the committed tile pyramid."""

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from print_layers import (
    build,
    choose_level,
    contour_lines,
    intervals_for,
    levels_for,
    read_tiles,
    soft_hillshade,
)

ROOT = Path(__file__).resolve().parents[1]
HAS_TILES = (ROOT / "data/out/north_sea/tiles/tiles.json").exists()


def test_intervals_grow_with_scale_and_levels_skip_zero():
    sea = [intervals_for(s)[0] for s in (1e5, 5e5, 1.5e6, 5e6, 2e7)]
    assert sea == sorted(sea) and sea[0] < sea[-1]
    lv = levels_for(-350, 520, 100, 200)
    assert 0 not in lv and lv == [-300, -200, -100, 200, 400]


def test_flat_ground_is_neutral_and_slopes_light_by_aspect():
    flat = soft_hillshade(np.zeros((20, 20), "float32"), 150)
    assert np.allclose(flat, 1.0, atol=1e-6)
    x = np.arange(40, dtype="float32")
    ramp_down_to_se = np.tile(-x * 30, (40, 1)) + (
        -x[:, None] * 30
    )  # falls towards the south-east
    nw_facing = soft_hillshade(-ramp_down_to_se, 150)[
        20, 20
    ]  # rises towards the south-east, so faces the north-west
    se_facing = soft_hillshade(ramp_down_to_se, 150)[20, 20]
    assert nw_facing > 1.0 > se_facing  # lit from the north-west


def test_contours_of_a_cone_are_closed_nested_and_generalised():
    y, x = np.mgrid[-200:200, -200:200].astype("float32")
    z = np.maximum(0, 600 - np.hypot(x, y) * 4)  # 600 m cone, 150 m cells
    tr = rasterio.Affine(150, 0, 0, 0, -150, 0)
    lines = contour_lines(z, tr, [200.0, 400.0], 1_000_000)
    assert set(lines) == {200.0, 400.0}
    for parts in lines.values():
        assert len(parts) == 1 and np.allclose(
            parts[0][0], parts[0][-1]
        )  # one closed ring per level
    r = {
        lv: np.hypot(*(lines[lv][0] - lines[lv][0].mean(axis=0)).T).mean()
        for lv in lines
    }
    assert r[400.0] < r[200.0]
    assert len(lines[200.0][0]) < 400  # thinned: not one vertex per cell


def test_choose_level_is_coarsest_that_is_fine_enough():
    levels = [{"cell": c, "z": i} for i, c in enumerate([600, 300, 150])]
    assert choose_level(levels, 400)["cell"] == 300
    assert (
        choose_level(levels, 100)["cell"] == 150
    )  # data finer than the pixel is not available: use the finest
    assert choose_level(levels, 1000)["cell"] == 600


@pytest.mark.skipif(not HAS_TILES, reason="tile pyramid not built")
def test_tiles_window_matches_demo_texture_region():
    z, tr, src = read_tiles("north_sea", (100000, 6500000, 140000, 6540000), 600)
    assert src["kind"] == "tiles" and src["cell"] <= 600
    assert abs(z.shape[0] - 40000 / tr.a) <= 2 and abs(z.shape[1] - 40000 / tr.a) <= 2  # snapped out to whole cells
    assert -1000 < z.min() < z.max() < 2500


@pytest.mark.skipif(not HAS_TILES, reason="tile pyramid not built")
def test_build_writes_all_layers_and_manifest(tmp_path):
    ext = (0, 6350000, 80000, 6430000)
    m = build(
        "north_sea",
        500_000,
        150,
        tmp_path,
        extent=ext,
        layers=("elevation", "zones", "hillshade", "contours", "coast"),
    )
    for f in (
        "elevation.tif",
        "zones.tif",
        "hillshade.tif",
        "contours.geojson",
        "coast.geojson",
        "layers.json",
    ):
        assert (tmp_path / f).exists(), f
    assert m["files"]["contours"]["interval_sea_m"] == 50.0
    with rasterio.open(tmp_path / "hillshade.tif") as r:
        assert (
            r.dtypes[0] == "uint8" and r.crs is not None and 0 < r.read(1).mean() < 160
        )
    gj = json.loads((tmp_path / "contours.geojson").read_text())
    zs = {f["properties"]["z"] for f in gj["features"]}
    assert 0 not in zs and all(abs(z) % 50 == 0 for z in zs)
    assert json.loads((tmp_path / "layers.json").read_text())["attribution"]
