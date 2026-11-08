"""Packaging and fetching of data releases, without the network."""

import json
import tarfile

import fetch_data as fd
import publish_data as pd
import pytest


def fake_out(tmp_path, regions=("north_sea", "vestland")):
    out = tmp_path / "out"
    for rid in regions:
        (out / rid / "demo").mkdir(parents=True)
        (out / rid / "tiles" / "0").mkdir(parents=True)
        (out / rid / "demo" / "elev.webp").write_bytes(b"elev-" + rid.encode())
        (out / rid / "demo" / "meta.json").write_text(json.dumps({"cell": 500, "data": {"sources": [{"id": "cop_glo30"}], "attribution": [f"© {rid} data"]}}))
        (out / rid / "tiles" / "tiles.json").write_text(json.dumps({"built": "2026-11-08", "levels": [{"cell": 1000}, {"cell": 150}]}))
        (out / rid / "tiles" / "0" / "0_0.webp").write_bytes(b"tile")
        (out / rid / ".data-release").write_text("old")  # markers are local bookkeeping, never packed
    return out


def test_build_packs_each_region_with_a_verifiable_manifest(tmp_path):
    out, dist = fake_out(tmp_path), tmp_path / "dist"
    m = pd.build(out, dist, tag="data-test")
    assert list(m["regions"]) == ["north_sea"]  # vestland is committed to git, not released
    e = m["regions"]["north_sea"]
    assert e["sha256"] == pd.sha256(dist / e["file"]) and e["files"] == 4 and e["finest_cell_m"] == 150 and e["tiles"] is True
    assert e["sources"] == ["cop_glo30"] and e["attribution"] == ["© north_sea data"]
    assert json.loads((dist / "manifest.json").read_text())["regions"]["north_sea"]["bytes"] == e["bytes"]
    with tarfile.open(dist / e["file"]) as tar:
        assert all(n.startswith("north_sea/") and ".data-release" not in n for n in tar.getnames())


def test_a_named_region_can_be_packed_even_if_it_is_in_git(tmp_path):
    out = fake_out(tmp_path)
    assert list(pd.build(out, tmp_path / "d", ["vestland"])["regions"]) == ["vestland"]
    with pytest.raises(SystemExit):
        pd.build(out, tmp_path / "d", ["atlantis"])


def test_fetch_round_trip_restores_every_file(tmp_path):
    out, dist = fake_out(tmp_path), tmp_path / "dist"
    e = pd.build(out, dist)["regions"]["north_sea"]
    dest = tmp_path / "restored"
    names = fd.verify_and_extract(dist / e["file"], e["sha256"], dest)
    assert len(names) == 4
    for p in (out / "north_sea").rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            assert (dest / "north_sea" / p.relative_to(out / "north_sea")).read_bytes() == p.read_bytes()


def test_a_corrupt_download_is_refused(tmp_path):
    out, dist = fake_out(tmp_path), tmp_path / "dist"
    e = pd.build(out, dist)["regions"]["north_sea"]
    with pytest.raises(SystemExit, match="checksum mismatch"):
        fd.verify_and_extract(dist / e["file"], "0" * 64, tmp_path / "dest")
    assert not (tmp_path / "dest" / "north_sea").exists()


def test_an_archive_cannot_write_outside_the_destination(tmp_path):
    evil = tmp_path / "evil.tar.gz"
    payload = tmp_path / "payload.txt"
    payload.write_text("x")
    with tarfile.open(evil, "w:gz") as tar:
        tar.add(payload, arcname="../escaped.txt")
    with pytest.raises(SystemExit, match="outside"):
        fd.verify_and_extract(evil, fd.sha256(evil), tmp_path / "dest")
    assert not (tmp_path / "escaped.txt").exists()


def test_release_selection():
    rels = [{"tag_name": "v1.0", "draft": False}, {"tag_name": "data-2026-12-01", "draft": True},
            {"tag_name": "data-2026-11-08", "draft": False}, {"tag_name": "data-2026-10-01", "draft": False}]
    assert fd.pick_release(rels)["tag_name"] == "data-2026-11-08"  # newest published data release; drafts and code tags skipped
    assert fd.pick_release(rels, "data-2026-10-01")["tag_name"] == "data-2026-10-01"
    assert fd.pick_release(rels, "data-1999") is None and fd.pick_release([{"tag_name": "v2"}]) is None


def test_release_notes_and_dry_run(tmp_path, capsys):
    dist = tmp_path / "dist"
    m = pd.build(fake_out(tmp_path), dist)
    text = pd.release_notes(m)
    assert "© north_sea data" in text and "Not for navigation" in text and "| north_sea |" in text
    pd.release(dist, "data-test", "owner/repo", dry_run=True)
    assert "gh release create data-test" in capsys.readouterr().out
    assert json.loads((dist / "manifest.json").read_text())["tag"] == "data-test"
    assert (dist / "release-notes.md").exists()
