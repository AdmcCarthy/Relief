"""Fine windows: the list is consistent and every built window carries its cell size and attribution."""

import json
from pathlib import Path

import pytest

from regions import load

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = json.loads((ROOT / "regions" / "windows.json").read_text())["windows"]
FRAMES = {r["id"] for r in load()["regions"]}


def test_windows_are_unique_and_sit_in_registered_frames():
    names = [w["name"] for w in WINDOWS]
    assert len(names) == len(set(names))
    assert {w["frame"] for w in WINDOWS} <= FRAMES


@pytest.mark.parametrize("w", WINDOWS, ids=lambda w: w["name"])
def test_built_window_records_cell_and_attribution(w):
    js = ROOT / "data" / "raw" / w["frame"] / "windows" / f"{w['name']}.json"
    if not js.exists():
        pytest.skip("window not built on this machine (scripts/window.py run --all)")
    p = json.loads(js.read_text())
    assert p["cell_m"] <= 120 and "EMODnet" in p["attribution"] and p["licence"]
    assert p["valid_share"] > 0.99
