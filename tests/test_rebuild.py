"""The rebuild orchestrator's decisions, on a temporary tree and a fake runner (nothing is built or fetched)."""

import json
import os
import types

import pytest
import rebuild as rb

REGION = "r1"


def tree(tmp_path, *, lods=("overview", "regional", "detail"), base=True):
    raw, out = tmp_path / "data" / "raw" / REGION, tmp_path / "data" / "out" / REGION
    for d in (raw, out / "demo", out / "tiles"):
        d.mkdir(parents=True, exist_ok=True)
    (raw / "hires.tif").write_bytes(b"grid-v1")
    for p in ("demo/elev.webp", "demo/zones.png", "demo/meta.json", "tiles/tiles.json", "regional_base_light.png", "regional_base_dark.png"):
        (out / p).write_bytes(b"x")
    for n in lods:
        (out / f"{n}.geojson").write_text("{}")
    (out / "manifest.json").write_text(json.dumps({"lods": {n: {} for n in lods}, **({"base": {}} if base else {})}))
    now = os.stat(raw / "hires.tif").st_mtime
    for p in out.rglob("*"):
        if p.is_file():
            os.utime(p, (now + 10, now + 10))  # outputs newer than the grid
    return raw, out


def runs(steps):
    return {s.stage: s.reason for s in steps if s.run}


def test_a_current_tree_needs_nothing(tmp_path):
    tree(tmp_path)
    assert runs(rb.plan(tmp_path, [REGION])) == {}


def test_a_missing_grid_is_reported_and_everything_after_it_is_stale(tmp_path):
    raw, _ = tree(tmp_path)
    (raw / "hires.tif").unlink()
    r = runs(rb.plan(tmp_path, [REGION]))
    assert r["grids"].startswith("grid missing") and set(r) == {"grids", "render", "tiles", "vectors", "base"}


def test_without_a_stamp_file_times_decide(tmp_path):
    raw, _ = tree(tmp_path)
    os.utime(raw / "hires.tif", (os.stat(raw / "hires.tif").st_mtime + 100,) * 2)
    r = runs(rb.plan(tmp_path, [REGION]))
    assert set(r) == {"render", "tiles", "vectors", "base"} and "no stamp" in r["render"] and r["base"] == "render was rebuilt"


def test_a_stamp_ignores_a_new_timestamp_but_not_new_content(tmp_path):
    raw, _ = tree(tmp_path)
    for st in ("render", "tiles", "vectors", "base"):
        rb.record(tmp_path, REGION, st)
    os.utime(raw / "hires.tif", (os.stat(raw / "hires.tif").st_mtime + 500,) * 2)  # re-merged, same bytes
    assert runs(rb.plan(tmp_path, [REGION])) == {}
    (raw / "hires.tif").write_bytes(b"grid-v2")
    r = runs(rb.plan(tmp_path, [REGION]))
    assert r["render"] == "input changed" and r["tiles"] == "input changed" and r["vectors"] == "input changed" and "base" in r


def test_base_reruns_when_vectors_dropped_its_manifest_entry(tmp_path):
    tree(tmp_path, base=False)
    assert runs(rb.plan(tmp_path, [REGION])) == {"base": "manifest.json has no base entry"}


def test_a_region_without_a_detail_level_is_not_missing_one(tmp_path):
    tree(tmp_path, lods=("overview", "regional"))
    assert runs(rb.plan(tmp_path, [REGION])) == {}


def test_force_from_and_only(tmp_path):
    tree(tmp_path)
    assert set(runs(rb.plan(tmp_path, [REGION], force=True))) == set(rb.NAMES)
    assert set(runs(rb.plan(tmp_path, [REGION], start="vectors"))) == {"vectors", "base"}
    assert set(runs(rb.plan(tmp_path, [REGION], force=True, only=["tiles"]))) == {"tiles"}


def test_execute_runs_stale_stages_in_order_and_records_stamps(tmp_path):
    _, out = tree(tmp_path)
    (out / "tiles" / "tiles.json").unlink()
    calls = []
    ok = lambda cmd, cwd: calls.append((cmd[1].split("/")[-1], cmd[2], cwd)) or types.SimpleNamespace(returncode=0)  # noqa: E731
    res = rb.execute(tmp_path, rb.plan(tmp_path, [REGION]), download=False, runner=ok, log=lambda *_: None)
    assert res == {REGION: "ok"} and calls == [("build_tiles.py", REGION, tmp_path)]
    assert "tiles" in rb.read_stamps(tmp_path, REGION)


def test_a_failed_stage_stops_that_region_and_leaves_no_stamp(tmp_path):
    _, out = tree(tmp_path)
    (out / "demo" / "elev.webp").unlink()
    seen = []
    bad = lambda cmd, cwd: seen.append(cmd[1]) or types.SimpleNamespace(returncode=1)  # noqa: E731
    res = rb.execute(tmp_path, rb.plan(tmp_path, [REGION]), download=False, runner=bad, log=lambda *_: None)
    assert res == {REGION: "failed: render"} and len(seen) == 1 and "render" not in rb.read_stamps(tmp_path, REGION)


def test_a_missing_grid_blocks_unless_download_is_asked_for(tmp_path):
    raw, _ = tree(tmp_path)
    (raw / "hires.tif").unlink()
    never = lambda *a, **k: pytest.fail("nothing may run without a grid")  # noqa: E731
    res = rb.execute(tmp_path, rb.plan(tmp_path, [REGION]), download=False, runner=never, log=lambda *_: None)
    assert res[REGION].startswith("blocked")
    cmd = rb.command("grids", REGION, True)
    assert cmd[2:] == ["--grids", REGION, "--force"] and rb.command("grids", REGION, False) is None


def test_vestland_is_left_out_of_the_default_set_and_the_registry_is_readable():
    assert "vestland" in rb.IN_GIT
    assert {"north_sea", "world"} <= set(rb.regions_in_registry(rb.ROOT))
