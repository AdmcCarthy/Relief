"""The Köppen-Geiger raster is fetched on demand, so the renderers need no manual install."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_climate  # noqa: E402
import render_demo  # noqa: E402
import render_region  # noqa: E402


def test_ensure_returns_an_existing_file_without_downloading(tmp_path, monkeypatch):
    tif = tmp_path / "k.tif"
    tif.write_bytes(b"x")
    monkeypatch.setattr(fetch_climate.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("downloaded")))
    assert fetch_climate.ensure(tif) == tif


def test_renderers_go_through_ensure():
    for mod in (render_region, render_demo):
        assert mod.fetch_climate is fetch_climate
        assert "fetch_climate.ensure()" in Path(mod.__file__).read_text(encoding="utf-8")


def test_source_is_pinned_and_licensed():
    assert fetch_climate.URL.startswith("https://ndownloader.figshare.com/") and len(fetch_climate.MD5) == 32
