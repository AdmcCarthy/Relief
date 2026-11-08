"""Tile pyramid: level maths, tile contents, built pyramids, and static checks on the page scripts (which cannot be run here)."""

import itertools
import json
import re
from pathlib import Path

import build_tiles as bt
import numpy as np
import pytest
import render_region as rr

from regions import load

ROOT = Path(__file__).resolve().parents[1]
REGIONS = {r["id"]: r for r in load()["regions"]}
BUILT = [r for r in REGIONS if (ROOT / "data" / "out" / r / "tiles" / "tiles.json").exists()]


def test_levels_halve_until_one_tile():
    lv = bt.level_sizes(3000, 2401, 250)
    assert lv[0]["grid"] == [1, 1] and max(lv[0]["size"]) <= bt.TILE
    assert lv[-1]["size"] == [3000, 2401] and lv[-1]["cell"] == 250
    for coarse, fine in itertools.pairwise(lv):
        assert coarse["cell"] == fine["cell"] * 2
        assert coarse["size"] == [-(-fine["size"][0] // 2), -(-fine["size"][1] // 2)]
    assert [x["z"] for x in lv] == list(range(len(lv)))
    assert lv[-1]["grid"] == [6, 5]  # ceil(3000/512), ceil(2401/512)


def test_a_grid_that_fits_one_tile_has_one_level():
    lv = bt.level_sizes(300, 200, 1000)
    assert len(lv) == 1 and lv[0]["grid"] == [1, 1]


def test_halve_is_a_block_mean_and_copes_with_odd_sizes():
    a = np.arange(5 * 7, dtype="float32").reshape(5, 7)
    h = bt.halve(a)
    assert h.shape == (3, 4)
    assert h[0, 0] == a[:2, :2].mean() and h[2, 3] == a[4, 6]  # the odd edge repeats its last row and column
    flat = np.full((6, 6), 12.5, dtype="float32")
    assert np.all(bt.halve(flat) == 12.5)


def test_tiles_hold_the_right_pixels_and_round_trip(tmp_path):
    rng = np.random.default_rng(1)
    z = (rng.normal(0, 400, (700, 1100))).astype("float32")
    z[:200] = np.abs(z[:200])
    lv = bt.level_sizes(1100, 700, 100)
    finest = lv[-1]
    bt.write_level(z, tmp_path / "f", finest["grid"])
    assert len(list((tmp_path / "f").glob("*.webp"))) == finest["grid"][0] * finest["grid"][1]
    for x, y in [(0, 0), (2, 1), (finest["grid"][0] - 1, finest["grid"][1] - 1)]:
        tile = rr.decode((tmp_path / "f" / f"{x}_{y}.webp").read_bytes())
        want = z[y * 512:(y + 1) * 512, x * 512:(x + 1) * 512]
        assert tile.shape == want.shape
        assert np.max(np.abs(tile - want)) <= rr.STEP / 2 + 1e-3  # float32 input


def test_tile_of_maps_metres_to_tiles():
    doc = {"extent": [1000.0, 5000.0, 21000.0, 15000.0], "tile": 512, "levels": [{"cell": 100.0}, {"cell": 50.0}]}
    assert bt.tile_of(doc, 1, 1000.0, 15000.0) == (0, 0)  # north-west corner
    assert bt.tile_of(doc, 1, 1000.0 + 50 * 512, 15000.0 - 50 * 512) == (1, 1)
    assert bt.tile_of(doc, 0, 20999.0, 5001.0) == (0, 0)  # 100 m cells: the whole region is 200 x 100 px


@pytest.mark.parametrize("rid", BUILT)
def test_built_pyramid_is_complete_and_matches_the_region(rid):
    folder = ROOT / "data" / "out" / rid / "tiles"
    doc = json.loads((folder / "tiles.json").read_text())
    assert doc["extent"] == REGIONS[rid]["extent"] and doc["tile"] == bt.TILE
    assert doc["levels"][0]["grid"] == [1, 1]
    total = 0
    for lv in doc["levels"]:
        files = list((folder / str(lv["z"])).glob("*.webp"))
        assert len(files) == lv["grid"][0] * lv["grid"][1], f"{rid} level {lv['z']} is missing tiles"
        total += sum(f.stat().st_size for f in files)
    assert total == doc["total_bytes"]
    assert total / 1e6 <= 80, f"{rid} pyramid is {total / 1e6:.0f} MB: too heavy to commit"
    first = rr.decode((folder / "0" / "0_0.webp").read_bytes())
    assert first.shape == (doc["levels"][0]["size"][1], doc["levels"][0]["size"][0])
    assert (first > 0).any() and (first < 0).any()


# ---------------------------------------------------------------- the page scripts, checked statically
PAGES = [("explore.html", "explore.js"), ("index.html", "regions.js")]


@pytest.mark.parametrize(("html", "js"), PAGES)
def test_script_only_uses_element_ids_that_exist(html, js):
    page = (ROOT / "preview" / html).read_text()
    code = (ROOT / "preview" / js).read_text()
    ids = set(re.findall(r'\$\("([\w-]+)"\)', code)) | set(re.findall(r'getElementById\("([\w-]+)"\)', code))
    missing = [i for i in ids if f'id="{i}"' not in page]
    assert not missing, f"{js} uses ids missing from {html}: {missing}"


@pytest.mark.parametrize("js", ["explore.js", "regions.js", "demo.js", "palette.js", "geo.js", "relief.js"])
def test_imports_resolve_and_names_are_exported(js):
    code = (ROOT / "preview" / js).read_text()
    for names, mod in re.findall(r'import \{([^}]*)\} from "\./([\w.]+)"', code):
        exported = (ROOT / "preview" / mod).read_text()
        for n in [x.strip() for x in names.split(",") if x.strip()]:
            assert re.search(rf"export (?:function {n}\b|(?:const|let) [^;\n]*\b{n}\b)|export \{{[^}}]*\b{n}\b", exported), f"{js} imports {n}, not exported by {mod}"


@pytest.mark.parametrize("js", ["explore.js", "regions.js", "palette.js", "geo.js", "relief.js", "demo.js"])
def test_brackets_balance(js):
    code = (ROOT / "preview" / js).read_text()
    code = re.sub(r"/\[[^\]\n]*\]/[a-z]*", "0", code)  # regex literals with a character class
    code = re.sub(r"`(?:\\.|[^`\\])*`", "``", code)  # template literals may hold anything
    code = re.sub(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', '""', code)
    code = re.sub(r"//[^\n]*", "", code)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    for a, b in ("()", "[]", "{}"):
        assert code.count(a) == code.count(b), f"{js}: unbalanced {a}{b}"
