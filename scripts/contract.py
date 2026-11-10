"""The consumer contract: what other repos can rely on in a Relief release and in a built region folder.

Version 1. Consumers (SubScout, Sheet, Bedrock, source-to-sink, ...) pin a release tag and read only the keys named here;
anything else in a manifest is private and may change. A change that removes or renames a listed key, or changes what it
means, raises CONTRACT and ships in a new release tag; adding keys does not. Written down in docs/consuming-relief.md.

  python scripts/contract.py check [data/out] [region ...]   # validate built region folders; exit 1 on a problem
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CONTRACT = 1

RELEASE_KEYS = {"schema", "tag", "created", "licence", "regions"}
ENTRY_KEYS = {
    "data": {"file", "sha256", "bytes", "files", "unpacked_bytes", "finest_cell_m", "tiles", "built", "sources", "attribution"},
    "grids": {"file", "sha256", "bytes", "files", "unpacked_bytes", "cell_m", "size", "built", "land_sources", "sea_sources", "attribution"},
}
REGION_MANIFEST_KEYS = {"area", "name", "crs", "extent", "bbox", "land", "sea", "lods"}
LOD_KEYS = {"cell", "bounds", "shape"}
TILES_KEYS = {"region", "crs", "extent", "tile", "encoding", "levels", "attribution"}
LEVEL_KEYS = {"cell", "size", "z", "grid"}
META_KEYS = {"area", "crs", "bounds", "size", "zmin", "zmax", "encoding", "data"}
ENCODING_KEYS = {"base", "step", "channels"}


def _missing(obj, keys: set[str], where: str) -> list[str]:
    if not isinstance(obj, dict):
        return [f"{where}: expected an object"]
    return [f"{where}: missing '{k}'" for k in sorted(keys - obj.keys())]


def release_kind(manifest: dict) -> str:
    return manifest.get("kind", "data")  # releases made before the grids series carry no 'kind'


def check_release_manifest(manifest: dict) -> list[str]:
    """Problems in a data-* or grids-* release manifest (empty list = fine)."""
    problems = _missing(manifest, RELEASE_KEYS, "manifest")
    if problems and not isinstance(manifest, dict):
        return problems
    if manifest.get("contract", 1) > CONTRACT:
        problems.append(f"manifest: contract {manifest['contract']} is newer than this checkout understands ({CONTRACT})")
    kind = release_kind(manifest)
    if kind not in ENTRY_KEYS:
        return problems + [f"manifest: unknown kind '{kind}'"]
    for rid, e in (manifest.get("regions") or {}).items():
        problems += _missing(e, ENTRY_KEYS[kind], f"regions.{rid}")
        if isinstance(e, dict) and isinstance(e.get("sha256"), str) and len(e["sha256"]) != 64:
            problems.append(f"regions.{rid}: sha256 is not 64 hex characters")
    return problems


def _load(path: Path, problems: list[str]) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        problems.append(f"{path.name}: cannot read ({err.__class__.__name__})")
        return None


def check_region_dir(region_dir: Path) -> list[str]:
    """Problems in one built region folder (data/out/<region>): required keys, and that every file they name exists."""
    rid, problems = region_dir.name, []
    man = _load(region_dir / "manifest.json", problems)
    if man is not None:
        problems += _missing(man, REGION_MANIFEST_KEYS, f"{rid}/manifest.json")
        for name, lod in (man.get("lods") or {}).items():
            problems += _missing(lod, LOD_KEYS, f"{rid}/manifest.json lods.{name}")
            problems += [f"{rid}: {name}{s} is missing" for s in (".geojson", "_hillshade.png") if not (region_dir / f"{name}{s}").exists()]
        for theme, fn in ((man.get("base") or {}).get("regional") or {}).items():
            if not (region_dir / fn).exists():
                problems.append(f"{rid}: base image {fn} ({theme}) is missing")
    if (region_dir / "demo" / "meta.json").exists():
        meta = _load(region_dir / "demo" / "meta.json", problems)
        if meta is not None:
            problems += _missing(meta, META_KEYS, f"{rid}/demo/meta.json") + _missing(meta.get("encoding"), ENCODING_KEYS, f"{rid}/demo/meta.json encoding")
            problems += [f"{rid}: demo/{f} is missing" for f in ("elev.webp", "zones.png") if not (region_dir / "demo" / f).exists()]
    if (region_dir / "tiles" / "tiles.json").exists():
        t = _load(region_dir / "tiles" / "tiles.json", problems)
        if t is not None:
            problems += _missing(t, TILES_KEYS, f"{rid}/tiles/tiles.json")
            for lv in t.get("levels") or []:
                problems += _missing(lv, LEVEL_KEYS, f"{rid}/tiles/tiles.json level")
                if not LEVEL_KEYS - lv.keys():
                    gx, gy = lv["grid"]
                    gone = [f"{x}_{y}" for x in range(gx) for y in range(gy) if not (region_dir / "tiles" / str(lv["z"]) / f"{x}_{y}.webp").exists()]
                    if gone:
                        problems.append(f"{rid}: {len(gone)} tile(s) missing at level {lv['z']} (first {gone[0]})")
    return problems


IN_GIT = {"vestland"}  # the older proof of concept kept in git: not part of any release, so not held to the contract unless named


def check_out(out_root: Path, regions: list[str] | None = None) -> dict[str, list[str]]:
    ids = regions or sorted(p.name for p in out_root.iterdir() if p.is_dir() and (p / "manifest.json").exists() and p.name not in IN_GIT)
    return {rid: check_region_dir(out_root / rid) for rid in ids}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "check":
        args = args[1:]
    root = Path(args[0]) if args else Path(__file__).resolve().parents[1] / "data" / "out"
    result = check_out(root, args[1:] or None)
    for rid, probs in result.items():
        print(f"{rid:14s} {'ok' if not probs else str(len(probs)) + ' problem(s)'}")
        for p in probs[:10]:
            print(f"  - {p}")
    sys.exit(1 if any(result.values()) else 0)
