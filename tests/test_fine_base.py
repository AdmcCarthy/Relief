"""The fine base is a whole-cell cut of the merged grid, coloured and shaded by the same rules as the regional base."""

import json
from pathlib import Path

import base_tint as bt
import fine_base as fb
import numpy as np
import pytest
from build import FLAT

ROOT = Path(__file__).resolve().parents[1]
REGIONS = {r["id"]: r for r in json.loads((ROOT / "regions" / "regions.json").read_text(encoding="utf-8"))["regions"]}
CG_FINE = [130000, 6060000, 800000, 6510000]  # the field-map area of docs/plan-central-graben-frames.md


def test_central_graben_extent_is_pinned():
    """A consumer cuts fixed views from this frame: the extent is exact, not rounded from a lon/lat box."""
    r = REGIONS["central_graben"]
    assert r["extent"] == [-115000, 6060000, 935000, 6510000]
    assert r["crs"]["epsg"] == 25831 and r["bathymetry"] == "shelf" and "role" not in r
    assert {k: v["cell"] for k, v in r["lods"].items()} == {"overview": 2000, "regional": 900, "detail": 300}


def test_fine_area_falls_on_whole_cells_of_the_125_m_grid():
    r0, r1, c0, c1 = fb.window_of(CG_FINE, REGIONS["central_graben"]["extent"], 125.0)
    assert (r0, r1, c0, c1) == (0, 3600, 1960, 7320)
    assert (c1 - c0, r1 - r0) == (5360, 3600)


def test_window_refuses_a_cut_off_the_cell_lattice_or_outside_the_grid():
    grid = [0, 0, 1000, 500]
    assert fb.window_of([100, 100, 300, 400], grid, 100) == (1, 4, 1, 3)
    with pytest.raises(ValueError):
        fb.window_of([150, 100, 300, 400], grid, 100)
    with pytest.raises(ValueError):
        fb.window_of([100, 100, 1100, 400], grid, 100)


def test_tint_uses_the_regional_ramps():
    z = np.array([[-1300.0, -100.0, -1.0], [1.0, 300.0, 2000.0]], dtype=np.float32)
    w = np.zeros(z.shape + (4,), dtype=np.float32)
    w[..., 0] = 1  # temperate
    t = fb.tints(z, w, "shelf")
    for theme in ("light", "dark"):
        assert t[theme].dtype == np.uint8 and t[theme].shape == (2, 3, 3)
        assert tuple(t[theme][0, 0]) == tuple(int(v) for v in bt.rgb(bt.DETUNED_SEA[theme][-1]))
        sea = bt.linear_ramp(-z[:1] / bt.SMAX, bt.SB, bt.DETUNED_SEA[theme], bt.SMAX)
        assert np.array_equal(t[theme][:1], np.round(sea).astype("uint8"))
        land = bt.linear_land(z[1:], w[1:], theme)
        assert np.array_equal(t[theme][1:], np.round(land).astype("uint8"))


def test_neutral_shade_puts_flat_ground_at_mid_grey_and_stretches_slopes():
    s = np.array([[FLAT, FLAT + 10 / 255, FLAT - 10 / 255, 0.0, 1.0]], dtype=np.float32)
    assert fb.neutral(s).tolist() == [[128, 153, 103, 0, 255]]
