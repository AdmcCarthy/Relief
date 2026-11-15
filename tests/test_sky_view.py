"""sky_view: the sky-view factor and the `sky` shade model (neutrality, hollows, light direction, speed)."""

import time
from pathlib import Path

import numpy as np
import pytest
from print_layers import build
from sky_view import (
    AMBIENT,
    DIRECTIONS,
    search_cells,
    sector_weights,
    sky_hillshade,
    sky_view,
)

ROOT = Path(__file__).resolve().parents[1]
HAS_TILES = (ROOT / "data/out/north_sea/tiles/tiles.json").exists()


def test_sixteen_directions_share_the_compass():
    w = sector_weights()
    assert len(DIRECTIONS) == 16 and np.isclose(w.sum(), 1.0)
    assert (
        w.min() > 0.04 and w.max() < 0.08
    )  # diagonal 18.4, knight 22.5, cardinal 26.6 degrees of 360


def test_search_radius_is_about_20_km_within_bounds():
    assert (
        search_cells(200) == 100
        and search_cells(1600) == 16
        and search_cells(50) == 128
    )


def test_open_ground_sees_the_whole_sky():
    assert np.allclose(sky_view(np.zeros((40, 40), "float32"), 150), 1.0)
    y, x = np.mgrid[-40:40, -40:40].astype("float32")
    dome = np.maximum(0, 800 - np.hypot(x, y) * 20)
    svf = sky_view(dome, 150)
    assert svf[40, 40] == 1.0  # nothing stands above a summit


def test_a_bowl_floor_sees_less_sky_than_its_rim():
    y, x = np.mgrid[-40:40, -40:40].astype("float32")
    bowl = np.minimum(
        0, np.hypot(x, y) * 25 - 600
    )  # 600 m deep, 150 m cells, 24 cells to the rim
    svf = sky_view(bowl, 150)
    assert svf[40, 40] < 0.8 < svf[2, 2] == 1.0


def test_sky_shade_is_neutral_on_open_ground_and_keeps_the_light_direction():
    flat = sky_hillshade(np.zeros((30, 30), "float32"), 150)
    assert np.allclose(flat, 1.0, atol=1e-6)
    x = np.arange(40, dtype="float32")
    ramp = np.tile(-x * 30, (40, 1)) + (
        -x[:, None] * 30
    )  # falls towards the south-east
    nw_facing = sky_hillshade(-ramp, 150)[20, 20]
    se_facing = sky_hillshade(ramp, 150)[20, 20]
    assert nw_facing > se_facing > 0  # lit from the north-west
    # the sky light multiplies both faces of the same plane by the same factor, so the soft contrast is kept exactly
    from print_layers import soft_hillshade

    soft_ratio = soft_hillshade(-ramp, 150)[20, 20] / soft_hillshade(ramp, 150)[20, 20]
    assert np.isclose(nw_facing / se_facing, soft_ratio, rtol=1e-4)
    y, x = np.mgrid[-40:40, -40:40].astype("float32")
    bowl = np.minimum(0, np.hypot(x, y) * 25 - 600)
    assert (
        sky_hillshade(bowl, 150)[40, 40] < 1.0
    )  # the floor is flat, so only the sky term can darken it


def test_the_shipped_png_keeps_flat_ground_at_180():
    from build import FLAT, shade_png

    assert round(FLAT * 255) == 180
    assert np.allclose(shade_png(np.zeros((20, 20), "float32"), 250), FLAT)
    y, x = np.mgrid[-40:40, -40:40].astype("float32")
    bowl = np.minimum(0, np.hypot(x, y) * 25 - 600)
    assert (
        shade_png(bowl, 150)[40, 40] < FLAT
    )  # a hollow is darker than open ground, which the one-light PNG never showed


def test_a_million_cells_in_a_few_seconds():
    rng = np.random.default_rng(1)
    z = rng.normal(0, 200, (1000, 1000)).astype("float32")
    t0 = time.perf_counter()
    sky_view(z, 100)
    assert time.perf_counter() - t0 < 15  # about 1 s on a laptop; generous for CI


@pytest.mark.skipif(not HAS_TILES, reason="tile pyramid not built")
def test_print_layers_offers_the_sky_model(tmp_path):
    m = build(
        "north_sea",
        500_000,
        150,
        tmp_path,
        extent=(0, 6350000, 80000, 6430000),
        layers=("hillshade",),
        shade_model="sky",
    )
    hs = m["files"]["hillshade"]
    assert (
        hs["mode"] == "sky"
        and hs["sky_strength"] == AMBIENT
        and "directions" in hs["sky_view"]
    )
