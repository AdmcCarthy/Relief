"""Package the built regions as GitHub Release assets, so the git repository holds code and small files only.

Tiles, textures and vector layers are generated, already compressed and re-made whenever the sources improve; committing
them would add a full copy to history on every rebuild. Instead each region becomes one tarball plus a manifest.json
(sha256, sizes, sources, attribution) attached to a release tagged data-YYYY-MM-DD. The Pages workflow and anyone who
wants the tiles call scripts/fetch_data.py, which verifies and unpacks the latest data release into data/out/.

  python scripts/publish_data.py build [region ...]            # data/out/<region>/ -> dist/relief-data-<region>.tar.gz + manifest.json
  python scripts/publish_data.py release --tag data-2026-11-08 # gh release create with everything in dist/ (needs the gh CLI)

Vestland stays in git (small, and the tests use it), so it is not packaged by default.

A second, separate series carries the merged grids behind those layers (the slow fetch and merge stage), tagged grids-YYYY-MM-DD:

  python scripts/publish_data.py grids-build [region ...]          # data/raw/<region>/hires.* -> dist/grids/relief-grids-<region>.tar.gz
  python scripts/publish_data.py grids-release --tag grids-2026-11-10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_GIT = {"vestland"}  # regions whose outputs are committed
KOPPEN = "Beck et al. (2023) Köppen-Geiger climate classification 1991–2020, CC BY 4.0 (climate-zone textures)"
LICENCE_NOTE = ("Derived from open data under the licences listed per region (CC BY 4.0, Open Government Licence v3, "
                "Copernicus, public domain). Keep the attribution with any use. Not for navigation.")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def regions_to_pack(out_root: Path, wanted: list[str] | None) -> list[str]:
    found = sorted(p.name for p in out_root.iterdir() if p.is_dir() and (p / "demo" / "meta.json").exists())
    ids = wanted or [r for r in found if r not in IN_GIT]
    missing = [r for r in ids if r not in found]
    if missing:
        raise SystemExit(f"no built data in {out_root} for: {', '.join(missing)}")
    return ids


def pack_region(out_root: Path, rid: str, dist: Path) -> dict:
    """data/out/<rid>/ -> dist/relief-data-<rid>.tar.gz (members are '<rid>/...'); returns the manifest entry."""
    archive = dist / f"relief-data-{rid}.tar.gz"
    files = sorted(p for p in (out_root / rid).rglob("*") if p.is_file() and not p.name.startswith("."))
    with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
        for p in files:
            tar.add(p, arcname=f"{rid}/{p.relative_to(out_root / rid).as_posix()}", recursive=False)
    meta = json.loads((out_root / rid / "demo" / "meta.json").read_text())
    tiles = out_root / rid / "tiles" / "tiles.json"
    td = json.loads(tiles.read_text()) if tiles.exists() else None
    return {
        "file": archive.name, "sha256": sha256(archive), "bytes": archive.stat().st_size, "files": len(files),
        "unpacked_bytes": sum(p.stat().st_size for p in files),
        "finest_cell_m": td["levels"][-1]["cell"] if td else meta["cell"], "tiles": bool(td),
        "built": (td or meta).get("built"), "sources": [s["id"] for s in meta.get("data", {}).get("sources", [])],
        "attribution": meta.get("data", {}).get("attribution", []),
    }


def build(out_root: Path, dist: Path, wanted: list[str] | None = None, tag: str | None = None) -> dict:
    dist.mkdir(parents=True, exist_ok=True)
    for old in dist.glob("relief-data-*.tar.gz"):
        old.unlink()
    manifest = {"schema": 1, "tag": tag, "created": date.today().isoformat(), "licence": LICENCE_NOTE, "regions": {}}
    for rid in regions_to_pack(out_root, wanted):
        manifest["regions"][rid] = pack_region(out_root, rid, dist)
        e = manifest["regions"][rid]
        print(f"  {rid:14s} {e['bytes'] / 1e6:7.1f} MB packed ({e['unpacked_bytes'] / 1e6:.0f} MB, {e['files']} files, finest {e['finest_cell_m']:.0f} m)")
    (dist / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    return manifest


def release_notes(manifest: dict) -> str:
    lines = [f"Processed elevation layers for the Relief regions, built {manifest['created']}.", "",
             "Fetch and verify with `uv run python scripts/fetch_data.py`; rebuild from the sources with `scripts/build_hires.py`.", "",
             "| Region | Packed | Finest cell | Tiles |", "|---|---|---|---|"]
    for rid, e in manifest["regions"].items():
        lines.append(f"| {rid} | {e['bytes'] / 1e6:.0f} MB | {e['finest_cell_m']:.0f} m | {'yes' if e['tiles'] else 'no'} |")
    attrib = sorted({a for e in manifest["regions"].values() for a in e["attribution"]} | {KOPPEN})
    lines += ["", "**Attribution**", ""] + [f"- {a}" for a in attrib] + ["", manifest["licence"]]
    return "\n".join(lines)


def release(dist: Path, tag: str, repo: str | None, dry_run: bool) -> None:
    manifest = json.loads((dist / "manifest.json").read_text())
    manifest["tag"] = tag
    (dist / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    notes = dist / "release-notes.md"
    notes.write_text(release_notes(manifest))
    assets = sorted(dist.glob("relief-data-*.tar.gz")) + [dist / "manifest.json"]
    cmd = ["gh", "release", "create", tag, *map(str, assets), "--title", f"Relief data {manifest['created']}", "--notes-file", str(notes)]
    if repo:
        cmd += ["--repo", repo]
    print(" ".join(cmd[:4]), f"... ({len(assets)} assets)")
    if not dry_run:
        subprocess.run(cmd, check=True)


# ---------------------------------------------------------------- merged grids (a second release series, grids-YYYY-MM-DD)
# The slow stage is fetching and merging the sources into data/raw/<region>/hires.tif. The grids are packed per region so a
# new machine can skip that stage: scripts/fetch_data.py --grids restores them into data/raw/.
GRID_FILES = ("hires.tif", "hires.json", "hires_sources.png", "merged.tif", "merged.json")  # merged.* feeds render_region.py


def grid_regions(raw_root: Path, wanted: list[str] | None) -> list[str]:
    found = sorted(p.name for p in raw_root.iterdir() if p.is_dir() and (p / "hires.tif").exists() and (p / "hires.json").exists())
    ids = wanted or found
    missing = [r for r in ids if r not in found]
    if missing:
        raise SystemExit(f"no merged grid (hires.tif and hires.json) in {raw_root} for: {', '.join(missing)}")
    return ids


def refuse_restricted(rid: str, meta: dict, plan: dict) -> None:
    """A grid is a derived copy of its sources: refuse one built from a source that is not redistributable."""
    used = [*meta.get("land_sources", []), *meta.get("sea_sources", [])]
    bad = [s for s in used if plan["sources"].get(s, {}).get("redistributable") is False]
    if bad:
        raise SystemExit(f"{rid}: grid includes sources that are not redistributable ({', '.join(bad)}); rebuild without them")


def pack_grid(raw_root: Path, rid: str, dist: Path, plan: dict) -> dict:
    """data/raw/<rid>/{hires.tif, ...} -> dist/relief-grids-<rid>.tar.gz (members '<rid>/<file>'); returns the manifest entry."""
    meta = json.loads((raw_root / rid / "hires.json").read_text())
    refuse_restricted(rid, meta, plan)
    files = [raw_root / rid / n for n in GRID_FILES if (raw_root / rid / n).exists()]
    archive = dist / f"relief-grids-{rid}.tar.gz"
    with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
        for p in files:
            tar.add(p, arcname=f"{rid}/{p.name}", recursive=False)
    return {
        "file": archive.name, "sha256": sha256(archive), "bytes": archive.stat().st_size, "files": len(files),
        "unpacked_bytes": sum(p.stat().st_size for p in files), "cell_m": meta["cell_m"], "size": meta["size"], "built": meta.get("built"),
        "land_sources": meta.get("land_sources", []), "sea_sources": meta.get("sea_sources", []), "attribution": meta.get("attribution", []),
    }


def build_grids(raw_root: Path, dist: Path, plan: dict, wanted: list[str] | None = None) -> dict:
    dist.mkdir(parents=True, exist_ok=True)
    for old in dist.glob("relief-grids-*.tar.gz"):
        old.unlink()
    manifest = {"schema": 1, "kind": "grids", "tag": None, "created": date.today().isoformat(), "licence": LICENCE_NOTE, "regions": {}}
    for rid in grid_regions(raw_root, wanted):
        e = manifest["regions"][rid] = pack_grid(raw_root, rid, dist, plan)
        print(f"  {rid:14s} {e['bytes'] / 1e6:7.1f} MB packed ({e['unpacked_bytes'] / 1e6:.0f} MB, {e['files']} files, {e['cell_m']:.0f} m cell)")
    (dist / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    return manifest


def grid_notes(manifest: dict) -> str:
    lines = [f"Merged elevation grids for the Relief regions, built {manifest['created']}: the output of the slow fetch and merge stage.", "",
             "Restore them with `uv run python scripts/fetch_data.py --grids`, then render and tile without refetching the sources. "
             "They are the products of `scripts/build_hires.py`; the cached source pieces are not included.", "",
             "| Region | Packed | Cell | Grid |", "|---|---|---|---|"]
    for rid, e in manifest["regions"].items():
        lines.append(f"| {rid} | {e['bytes'] / 1e6:.0f} MB | {e['cell_m']:.0f} m | {e['size'][0]} x {e['size'][1]} |")
    attrib = sorted({a for e in manifest["regions"].values() for a in e["attribution"]})
    return "\n".join(lines + ["", "**Attribution**", ""] + [f"- {a}" for a in attrib] + ["", manifest["licence"]])


def release_grids(dist: Path, tag: str, repo: str | None, dry_run: bool) -> None:
    manifest = json.loads((dist / "manifest.json").read_text())
    manifest["tag"] = tag
    (dist / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    notes = dist / "release-notes.md"
    notes.write_text(grid_notes(manifest))
    assets = sorted(dist.glob("relief-grids-*.tar.gz")) + [dist / "manifest.json"]
    cmd = ["gh", "release", "create", tag, *map(str, assets), "--title", f"Relief merged grids {manifest['created']}", "--notes-file", str(notes)]
    if repo:
        cmd += ["--repo", repo]
    print(" ".join(cmd[:4]), f"... ({len(assets)} assets)")
    if not dry_run:
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    gb = sub.add_parser("grids-build")
    gb.add_argument("regions", nargs="*")
    gb.add_argument("--raw", default=str(ROOT / "data" / "raw"))
    gb.add_argument("--dist", default=str(ROOT / "dist" / "grids"))
    gr = sub.add_parser("grids-release")
    gr.add_argument("--tag", default=f"grids-{date.today().isoformat()}")
    gr.add_argument("--dist", default=str(ROOT / "dist" / "grids"))
    gr.add_argument("--repo")
    gr.add_argument("--dry-run", action="store_true")
    b = sub.add_parser("build")
    b.add_argument("regions", nargs="*")
    b.add_argument("--out", default=str(ROOT / "data" / "out"))
    b.add_argument("--dist", default=str(ROOT / "dist"))
    r = sub.add_parser("release")
    r.add_argument("--tag", default=f"data-{date.today().isoformat()}")
    r.add_argument("--dist", default=str(ROOT / "dist"))
    r.add_argument("--repo")
    r.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        build(Path(a.out), Path(a.dist), a.regions or None)
    elif a.cmd == "grids-build":
        build_grids(Path(a.raw), Path(a.dist), json.loads((ROOT / "regions" / "sources.json").read_text()), a.regions or None)
    elif a.cmd == "grids-release":
        release_grids(Path(a.dist), a.tag, a.repo, a.dry_run)
    else:
        release(Path(a.dist), a.tag, a.repo, a.dry_run)
