"""Fine windows: the list is consistent and every built window carries its cell size and attribution.

Three kinds: EMODnet windows in a registered frame (cell 120 m or finer, EMODnet attributed), Copernicus DEM windows
(frame `dem`, any land box, UTM) and GEBCO windows (frame `gebco`, any box, UTM), the last two written by `window.py dem` and
`window.py gebco` for a private landforms repo."""

import json
from pathlib import Path

import pytest

from regions import load

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = json.loads((ROOT / "regions" / "windows.json").read_text(encoding="utf-8"))["windows"]
FRAMES = {r["id"] for r in load()["regions"]}
BOX_FRAMES = {"dem": "Copernicus", "gebco": "GEBCO"}  # frames that are a source, not a registered region


def test_windows_are_unique_and_sit_in_registered_frames():
    names = [w["name"] for w in WINDOWS]
    assert len(names) == len(set(names))
    assert {w["frame"] for w in WINDOWS} <= FRAMES | set(BOX_FRAMES)


@pytest.mark.parametrize("w", WINDOWS, ids=lambda w: w["name"])
def test_built_window_records_cell_and_attribution(w):
    js = ROOT / "data" / "raw" / w["frame"] / "windows" / f"{w['name']}.json"
    if not js.exists():
        pytest.skip("window not built on this machine (scripts/window.py run --all, dem --all, gebco --all)")
    p = json.loads(js.read_text(encoding="utf-8"))
    assert p["licence"] and p["crs"] and p["extent"]
    if w["frame"] in BOX_FRAMES:
        assert BOX_FRAMES[w["frame"]] in p["attribution"] or BOX_FRAMES[w["frame"]] in p["source"]
        assert p["cell_m"] == w.get("cell", 90 if w["frame"] == "dem" else 450)
        assert p["valid_share"] > 0.85  # a rift-flank window holds sea with no height data
    else:
        assert p["cell_m"] <= 120 and "EMODnet" in p["attribution"]
        assert p["valid_share"] > 0.99
