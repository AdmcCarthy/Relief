"""The base-tint stops mirror preview/palette.js, and the tint follows the house style: linear sea, linear land."""

import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import base_tint as bt

JS = (ROOT / "preview" / "palette.js").read_text(encoding="utf-8")


def js_list(name: str, theme: str) -> list[str]:
    block = re.search(name + r"\s*=\s*\{(.*?)\n\};", JS, re.DOTALL).group(1)
    row = re.search(theme + r":\s*\[(.*?)\]", block, re.DOTALL).group(1)
    return re.findall(r'"(#[0-9a-f]{6})"', row)


def test_sea_stops_match_palette_js():
    for theme in ("light", "dark"):
        assert bt.DETUNED_SEA[theme] == js_list("DETUNED_SEA", theme)
        assert bt.DETUNED_OCEAN[theme] == js_list("DETUNED_OCEAN", theme)


def test_land_stops_match_palette_js():
    zpal = re.search(r"ZPAL = \{(.*?)\n\};", JS, re.DOTALL).group(1)
    for theme in ("light", "dark"):
        block = re.search(theme + r":\s*\{(.*?)\n  \}", zpal, re.DOTALL).group(1)
        for zone in bt.ZONES:
            assert bt.ZPAL[theme][zone] == re.findall(r'"(#[0-9a-f]{6})"', re.search(zone + r":\s*\[(.*?)\]", block).group(1))
    assert bt.LB == [int(v) for v in re.search(r"LB = \[(.*?)\]", JS).group(1).split(",")]
    assert bt.SB == [int(v) for v in re.search(r"SB = \[(.*?)\]", JS).group(1).split(",")]


def test_land_is_a_linear_gradient_and_the_stepped_option_still_classes():
    z = np.linspace(0, 2000, 401, dtype=np.float32)
    w = np.zeros(z.shape + (4,), dtype=np.float32)
    w[..., 0] = 1  # all temperate
    land = bt.linear_land(z, w, "light")
    assert len({tuple(c) for c in np.round(land).astype(int)}) > 100, "a gradient, not eight classes"
    assert np.abs(np.diff(land, axis=0)).max() < 3, "no jump larger than a few levels between neighbouring heights"
    assert np.allclose(land[0], bt.tune(bt.ZPAL["light"]["temperate"][0], 0.5, 0.08), atol=1)  # the stops are the zone ramp, tuned
    assert len({tuple(c) for c in np.round(bt.stepped_land(z, w, "light")).astype(int)}) == len(bt.LB)


def test_sea_is_linear_and_land_is_stepped():
    t = np.linspace(0, 1, 101, dtype=np.float32)
    sea = bt.linear_ramp(t, bt.SB, bt.DETUNED_SEA["light"], bt.SMAX)
    lum = sea @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    assert np.all(np.diff(lum) <= 1e-3), "sea lightness falls with depth, with no steps back"
    assert len(np.unique(np.round(lum, 1))) > 60, "the sea ramp is a gradient, not a few steps"
    z = np.linspace(0, 2000, 401, dtype=np.float32)
    w = np.zeros(z.shape + (4,), dtype=np.float32)
    w[..., 0] = 1  # all temperate
    land = bt.stepped_land(z, w, "light")
    assert len({tuple(c) for c in np.round(land).astype(int)}) == len(bt.LB), "one colour per height class"
