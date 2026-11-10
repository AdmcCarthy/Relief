"""Download the processed Relief layers from the latest data release and unpack them into data/out/.

The repository holds code only; the built tiles and textures are release assets (see scripts/publish_data.py). This script
reads the release's manifest.json, downloads each region's tarball, checks its sha256 and unpacks it. Public repositories
need no token; GITHUB_TOKEN (set automatically in Actions) only avoids API rate limits.

  python scripts/fetch_data.py                       # every region in the latest data-* release
  python scripts/fetch_data.py north_sea world       # just these
  python scripts/fetch_data.py --tag data-2026-11-08 --dest data/out --force
  python scripts/fetch_data.py --grids               # the merged grids from the latest grids-* release -> data/raw/ (skips the slow stage)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tarfile
import tempfile
from pathlib import Path

import requests
from contract import check_release_manifest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "AdmcCarthy/Relief"
API = "https://api.github.com"


def headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    return h


def pick_release(releases: list[dict], tag: str | None = None, prefix: str = "data-") -> dict | None:
    """The newest published release tagged `prefix`* (releases arrive newest first), or the one with exactly `tag`."""
    for r in releases:
        if r.get("draft"):
            continue
        if (tag and tag != "latest" and r["tag_name"] == tag) or ((not tag or tag == "latest") and r["tag_name"].startswith(prefix)):
            return r
    return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_and_extract(archive: Path, expected_sha: str, dest: Path) -> list[str]:
    """Check the checksum, then unpack; members that would land outside `dest` are refused. Returns the member names."""
    got = sha256(archive)
    if got != expected_sha:
        raise SystemExit(f"checksum mismatch for {archive.name}: expected {expected_sha[:12]}…, got {got[:12]}…")
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
        for n in names:
            if not (root / n).resolve().is_relative_to(root):
                raise SystemExit(f"refusing archive member outside the destination: {n}")
        tar.extractall(dest, filter="data")
    return names


def download(url: str, to: Path) -> None:
    with requests.get(url, headers={**headers(), "Accept": "application/octet-stream"}, stream=True, timeout=(15, 120)) as r:
        r.raise_for_status()
        with open(to, "wb") as f:
            f.writelines(r.iter_content(1 << 22))


def list_releases(releases: list[dict], repo: str) -> None:
    """Print each published data-* / grids-* release (newest first) with its regions, read from its manifest."""
    for r in releases:
        if r.get("draft") or not r["tag_name"].startswith(("data-", "grids-")):
            continue
        asset = next((x for x in r["assets"] if x["name"] == "manifest.json"), None)
        regions = "no manifest"
        if asset:
            try:
                regions = ", ".join(requests.get(asset["browser_download_url"], timeout=60).json()["regions"])
            except (requests.RequestException, ValueError, KeyError):
                regions = "manifest unreadable"
        print(f"{r['tag_name']:24s} {r['published_at'][:10]}  {regions}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("regions", nargs="*")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--tag", default="latest")
    ap.add_argument("--dest", default=None, help="default data/out, or data/raw with --grids")
    ap.add_argument("--grids", action="store_true", help="fetch the merged grids (grids-* releases) into data/raw instead of the built layers")
    ap.add_argument("--force", action="store_true", help="download even if this release is already unpacked, or a local grid exists")
    ap.add_argument("--list", action="store_true", help="list the published data-* and grids-* releases and their regions, then stop")
    a = ap.parse_args()
    prefix, marker_name = ("grids-", ".grids-release") if a.grids else ("data-", ".data-release")
    r = requests.get(f"{API}/repos/{a.repo}/releases", headers=headers(), params={"per_page": 30}, timeout=60)
    r.raise_for_status()
    if a.list:
        list_releases(r.json(), a.repo)
        return
    rel = pick_release(r.json(), a.tag, prefix)
    if not rel:
        sys.exit(f"no published {prefix}* release found in {a.repo} (tag {a.tag}); publish one with scripts/publish_data.py")
    assets = {x["name"]: x for x in rel["assets"]}
    if "manifest.json" not in assets:
        sys.exit(f"release {rel['tag_name']} has no manifest.json")
    manifest = requests.get(assets["manifest.json"]["browser_download_url"], timeout=60).json()
    problems = check_release_manifest(manifest)
    if problems:
        sys.exit(f"release {rel['tag_name']} does not match the consumer contract this checkout understands:\n  - " + "\n  - ".join(problems[:8]))
    dest = Path(a.dest or ROOT / "data" / ("raw" if a.grids else "out"))
    print(f"{a.repo} release {rel['tag_name']} ({manifest['created']}): {', '.join(manifest['regions'])}")
    for rid in a.regions or list(manifest["regions"]):
        if rid not in manifest["regions"]:
            sys.exit(f"{rid} is not in release {rel['tag_name']}")
        e = manifest["regions"][rid]
        marker = dest / rid / marker_name
        if marker.exists() and marker.read_text().strip() == f"{rel['tag_name']} {e['sha256']}" and not a.force:
            print(f"  {rid}: up to date")
            continue
        if a.grids and (dest / rid / "hires.tif").exists() and not marker.exists() and not a.force:
            print(f"  {rid}: a locally built grid is already there; keeping it (use --force to replace)")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / e["file"]
            print(f"  {rid}: downloading {e['bytes'] / 1e6:.0f} MB ...", flush=True)
            download(assets[e["file"]]["browser_download_url"], archive)
            verify_and_extract(archive, e["sha256"], dest)
        marker.write_text(f"{rel['tag_name']} {e['sha256']}\n")
        print(f"  {rid}: unpacked to {dest / rid}")


if __name__ == "__main__":
    main()
