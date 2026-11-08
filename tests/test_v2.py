"""Smoothing, combined sea floor and climate zones."""

import json
from pathlib import Path

import numpy as np
import pytest
import smooth
from shapely.geometry import LinearRing, Polygon

DEMO = Path(__file__).resolve().parents[1] / "data" / "out" / "vestland" / "demo"


@pytest.fixture
def ring():
    t = np.linspace(0, 2 * np.pi, 60, endpoint=False)
    r = 10 + 2 * np.sin(5 * t) + np.random.default_rng(1).normal(0, 0.3, t.size)
    p = np.column_stack([r * np.cos(t), r * np.sin(t)])
    return np.vstack([p, p[:1]])


def test_chaikin_closed_and_inside_hull(ring):
    q = smooth.chaikin(ring, 3)
    assert np.allclose(q[0], q[-1]) and len(q) == (len(ring) - 1) * 8 + 1
    hull = Polygon(ring).convex_hull.buffer(1e-9)
    assert all(hull.contains(Polygon(q).exterior.interpolate(d)) for d in np.linspace(0, Polygon(q).length, 50))


def test_catmull_rom_passes_through_points(ring):
    q = smooth.catmull_rom(ring, samples=4)
    for p in ring[:-1]:
        assert np.min(np.hypot(*(q - p).T)) < 1e-9
    assert LinearRing(q).is_simple


def test_simplifiers_reduce_and_stay_simple(ring):
    for q in (smooth.douglas_peucker(ring, 0.5), smooth.visvalingam(ring, 1.0)):
        assert 4 <= len(q) < len(ring) and np.allclose(q[0], q[-1]) and LinearRing(q).is_simple


def test_visual_contours_have_no_self_crossings():
    m = json.loads((DEMO / "contours_visual.json").read_text())["methods"]
    assert all(m[k]["self_intersecting_rings"] == 0 for k in m if k != "raw")
    assert m["blur_chaikin"]["points"] < 0.4 * m["raw"]["points"]


def test_combined_seabed_and_zones():
    from PIL import Image

    meta = json.loads((DEMO / "meta.json").read_text())
    ov = meta["seabed"]["overlap"]["kartverket"]
    assert abs(ov["median_diff_m"]) < 2 and ov["p90_abs_diff_m"] < 15  # sources agree where they overlap
    assert abs(sum(meta["seabed"]["share_of_sea"].values()) - 1) < 0.01
    z = np.array(Image.open(DEMO / "zones.png")).astype(int)
    assert z.shape[2] == 3 and z.sum(axis=2).min() >= 250 and z.sum(axis=2).max() <= 260
    sh = meta["zones"]["share_of_land"]
    assert sh["boreal"] > sh["temperate"] > sh["tundra"] > 0 and sh["arid"] == 0
