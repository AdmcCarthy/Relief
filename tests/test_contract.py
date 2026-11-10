"""The consumer contract: release manifests and built region folders keep the keys other repos read."""

import json
from pathlib import Path

import contract as ct
import fetch_data as fd
import publish_data as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILT = [p.name for p in (ROOT / "data" / "out").glob("*") if (p / "manifest.json").exists() and p.name not in ct.IN_GIT] if (ROOT / "data" / "out").exists() else []


def good_region(tmp_path, rid="r1"):
    d = tmp_path / rid
    (d / "demo").mkdir(parents=True)
    (d / "tiles" / "0").mkdir(parents=True)
    man = {"area": rid, "name": "R", "crs": "EPSG:3035", "extent": [0, 0, 1, 1], "bbox": [0, 0, 1, 1], "land": [0], "sea": [0],
           "lods": {"regional": {"cell": 4, "bounds": [0, 0, 1, 1], "shape": [2, 2]}}, "base": {"regional": {"light": "b.png"}}}
    (d / "manifest.json").write_text(json.dumps(man))
    for f in ("regional.geojson", "regional_hillshade.png", "b.png", "demo/elev.webp", "demo/zones.png", "tiles/0/0_0.webp"):
        (d / f).write_bytes(b"x")
    (d / "demo" / "meta.json").write_text(json.dumps({"area": rid, "crs": "x", "bounds": [0, 0, 1, 1], "size": [2, 2], "zmin": -1, "zmax": 1,
                                                       "encoding": {"base": -11000, "step": 0.5, "channels": "R,G"}, "data": {}}))
    (d / "tiles" / "tiles.json").write_text(json.dumps({"region": rid, "crs": "x", "extent": [0, 0, 1, 1], "tile": 512, "encoding": {}, "attribution": [],
                                                         "levels": [{"cell": 4, "size": [2, 2], "z": 0, "grid": [1, 1]}]}))
    return d


def test_a_complete_region_folder_passes(tmp_path):
    assert ct.check_region_dir(good_region(tmp_path)) == []


@pytest.mark.parametrize("gone,expect", [("regional.geojson", "regional.geojson is missing"), ("b.png", "base image b.png"),
                                         ("demo/elev.webp", "elev.webp is missing"), ("tiles/0/0_0.webp", "1 tile(s) missing at level 0")])
def test_a_missing_file_a_manifest_names_is_a_problem(tmp_path, gone, expect):
    d = good_region(tmp_path)
    (d / gone).unlink()
    assert any(expect in p for p in ct.check_region_dir(d))


def test_a_removed_manifest_key_is_a_problem(tmp_path):
    d = good_region(tmp_path)
    man = json.loads((d / "manifest.json").read_text())
    del man["extent"]
    (d / "manifest.json").write_text(json.dumps(man))
    assert ct.check_region_dir(d) == ["r1/manifest.json: missing 'extent'"]


def test_the_manifests_the_publisher_writes_meet_the_contract(tmp_path):
    from test_publish import fake_out, fake_raw  # the same fixtures the packaging tests use
    data = pd.build(fake_out(tmp_path), tmp_path / "d")
    grids = pd.build_grids(fake_raw(tmp_path), tmp_path / "g", {"sources": {}})
    for m in (data, grids):
        assert m["contract"] == ct.CONTRACT
    assert ct.check_release_manifest(data) == []
    assert ct.release_kind(data) == "data" and ct.check_release_manifest(grids) == [] and ct.release_kind(grids) == "grids"


def test_releases_made_before_the_contract_key_are_still_accepted(tmp_path):
    from test_publish import fake_out
    m = pd.build(fake_out(tmp_path), tmp_path / "d")
    del m["contract"]
    assert ct.check_release_manifest(m) == []


def test_a_newer_contract_or_a_broken_manifest_is_refused(tmp_path):
    from test_publish import fake_out
    m = pd.build(fake_out(tmp_path), tmp_path / "d")
    assert any("newer than this checkout" in p for p in ct.check_release_manifest({**m, "contract": ct.CONTRACT + 1}))
    broken = json.loads(json.dumps(m))
    del broken["regions"]["north_sea"]["sha256"]
    assert ct.check_release_manifest(broken) == ["regions.north_sea: missing 'sha256'"]
    assert ct.check_release_manifest({"regions": {}})  # missing top-level keys
    assert ct.check_release_manifest({**m, "kind": "nonsense"}) == ["manifest: unknown kind 'nonsense'"]


def test_listing_releases_reads_the_manifests(monkeypatch, capsys):
    class R:
        def json(self):
            return {"regions": {"north_sea": {}, "world": {}}}
    monkeypatch.setattr(fd.requests, "get", lambda *a, **k: R())
    fd.list_releases([{"tag_name": "grids-2026-11-10", "draft": False, "published_at": "2026-11-10T08:00:00Z", "assets": [{"name": "manifest.json", "browser_download_url": "u"}]},
                      {"tag_name": "v1.0", "draft": False, "published_at": "2026-01-01T00:00:00Z", "assets": []}], "o/r")
    out = capsys.readouterr().out
    assert "grids-2026-11-10" in out and "north_sea, world" in out and "v1.0" not in out


@pytest.mark.skipif(not BUILT, reason="no built regions in data/out (CI fetches them first)")
@pytest.mark.parametrize("rid", BUILT)
def test_every_built_region_meets_the_contract(rid):
    assert ct.check_region_dir(ROOT / "data" / "out" / rid) == []
