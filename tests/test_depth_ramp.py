"""The sea-floor colour ramps: the browser constants match the generator, lightness only falls with depth, and the ocean
ramp keeps a visible, even step across 1,000 to 6,500 m where the shelf ramp is a single colour."""

import itertools
import json
import math
import re
from pathlib import Path

import depth_ramp as dr
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "preview" / "palette.js").read_text()


def js_array(name: str, key: str | None = None) -> list:
    body = re.search(rf"{name}\s*=\s*(\{{.*?\}}|\[.*?\])\s*[;,]", JS, re.DOTALL).group(1)
    if key:
        body = re.search(rf'{key}:\s*(\[.*?\])', body, re.DOTALL).group(1)
    return json.loads(body.replace("'", '"'))


@pytest.mark.parametrize(("key", "table"), [("light", dr.OCEAN_LIGHT), ("dark", dr.OCEAN_DARK)])
def test_browser_ramp_matches_the_generator(key, table):
    assert js_array("DETUNED_OCEAN", key) == dr.ocean_hex(table)
    assert js_array("OCEAN_SB") == dr.ocean_breaks(table)


@pytest.mark.parametrize("table", [dr.OCEAN_LIGHT, dr.OCEAN_DARK])
def test_lightness_falls_steadily_with_depth_in_one_hue_family(table):
    labs = [dr.srgb_to_oklab(dr.rgb_of(h)) for h in dr.ocean_hex(table)]
    L = [lab[0] for lab in labs]
    assert all(a > b for a, b in itertools.pairwise(L)), "deeper must be darker, at every step"
    hues = [math.degrees(math.atan2(lab[2], lab[1])) % 360 for lab in labs[1:]]
    assert all(190 < h < 290 for h in hues), "blue to indigo only: a sequential ramp, not a rainbow"


@pytest.mark.parametrize(("name", "table"), [("light", dr.OCEAN_LIGHT), ("dark", dr.OCEAN_DARK)])
def test_ocean_ramp_shows_the_ridge_depths(name, table):
    stops = dr.ramp_stops(dr.ocean_breaks(table), dr.ocean_hex(table), 7000)
    steps = [e for d, e, _ in dr.step_table(stops, 7000, depths=range(1000, 6501, 500)) if d <= 6000]
    assert min(steps) >= 3.0, f"{name}: a 500 m depth step must stay visible (delta E x100 >= 3), got {min(steps):.1f}"
    assert max(steps) / min(steps) < 2.0, f"{name}: steps should be about even, not bunched in one depth range"
    ridge_to_plain = dr.srgb_to_oklab(dr.sample(stops, 2600, 7000)), dr.srgb_to_oklab(dr.sample(stops, 4600, 7000))
    assert 100 * np.linalg.norm(np.subtract(*ridge_to_plain)) > 12, "a ridge crest and the plain beside it must differ clearly"


def test_the_shelf_ramp_is_flat_beyond_its_top_which_is_why_basins_need_the_ocean_ramp():
    stops = dr.ramps()["shelf_light"]
    assert all(e == 0 for d, e, _ in dr.step_table(stops, dr.SHELF_MAX, depths=range(1500, 6501, 500)))


def test_regions_pick_their_scale():
    regions = {r["id"]: r for r in json.loads((ROOT / "regions" / "regions.json").read_text())["regions"]}
    assert {i for i, r in regions.items() if r["bathymetry"] == "ocean"} == {"world", "atlantic", "norwegian_sea"}
    for rid in ("world", "atlantic", "norwegian_sea"):
        assert max(regions[rid]["levels"]["sea"]) >= 5000, f"{rid}: vector sea levels must reach the abyssal plains"
