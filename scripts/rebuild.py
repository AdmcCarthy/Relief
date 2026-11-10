"""One command from a merged grid to a region's published layers, skipping what is already current.

The stages, in order (each region is done one at a time to stay inside memory):

  grids    data/raw/<region>/hires.tif   the slow fetch and merge (build_hires.py); restored from a grids-* release with --download
  render   demo/{elev.webp, zones.png, meta.json}     scripts/render_region.py
  tiles    tiles/tiles.json and the pyramid           scripts/build_tiles.py
  vectors  {overview,regional,detail}.geojson, hillshades, manifest.json    scripts/build.py
  base     regional_base_{light,dark}.png and manifest "base"               scripts/base_tint.py (after render and vectors)

A stage is stale when an output is missing, its inputs changed, or an upstream stage ran in this invocation. "Changed" means a
different content hash from the one recorded after the last successful run (data/out/<region>/.rebuild-stamps.json); with no
stamp yet it falls back to file times. `adopt` records the stamps for outputs you know are current. Nothing
touches the network unless --download is given, and that only fetches Relief's own grids-* release; fetching and merging the
source data stays with build_hires.py, which is never run from here.

  python scripts/rebuild.py plan [region ...]                 # what would run and why: no side effects
  python scripts/rebuild.py run [region ...] [--download]     # run the stale stages
  python scripts/rebuild.py run north_sea --from tiles        # this stage and later ones, whether stale or not
  python scripts/rebuild.py run --force --package             # everything, then dist/ tarballs (publish_data.py build)
  python scripts/rebuild.py adopt north_sea                   # record the current outputs as built from the current inputs

With no region, every region in regions/regions.json is considered except Vestland (committed to git, built by an older route).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
IN_GIT = {"vestland"}  # no merged grid; its layers are committed


@dataclass(frozen=True)
class Stage:
    name: str
    deps: tuple[str, ...]  # stages whose rerun forces this one


STAGES = [Stage("grids", ()), Stage("render", ("grids",)), Stage("tiles", ("grids",)), Stage("vectors", ("grids",)), Stage("base", ("render", "vectors"))]
NAMES = [s.name for s in STAGES]


def grid_of(root: Path, region: str) -> Path:
    """The elevation grid the layers are cut from: hires.tif, else the older coarse merged.tif (the 'auto' rule of render_region)."""
    raw = root / "data" / "raw" / region
    return raw / "hires.tif" if (raw / "hires.tif").exists() or not (raw / "merged.tif").exists() else raw / "merged.tif"


def vector_lods(out: Path) -> list[str]:
    """The LODs build.py wrote for this region (a region like the world has no 'detail'), else the usual three."""
    try:
        return list(json.loads((out / "manifest.json").read_text(encoding="utf-8"))["lods"])
    except (OSError, ValueError, KeyError):
        return ["overview", "regional", "detail"]


def outputs(root: Path, region: str, stage: str) -> list[Path]:
    out = root / "data" / "out" / region
    return {
        "grids": [grid_of(root, region)],
        "render": [out / "demo" / "elev.webp", out / "demo" / "zones.png", out / "demo" / "meta.json"],
        "tiles": [out / "tiles" / "tiles.json"],
        "vectors": [out / "manifest.json", *(out / f"{n}.geojson" for n in vector_lods(out))],
        "base": [out / "regional_base_light.png", out / "regional_base_dark.png"],
    }[stage]


def inputs(root: Path, region: str, stage: str) -> list[Path]:
    out = root / "data" / "out" / region
    grid = grid_of(root, region)
    return {"grids": [], "render": [grid], "tiles": [grid], "vectors": [grid],
            "base": [out / "demo" / "elev.webp", out / "demo" / "zones.png"]}[stage]


def newest(paths: list[Path]) -> float:
    return max((p.stat().st_mtime for p in paths if p.exists()), default=0.0)


def digest(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.name.encode())
        with open(p, "rb") as f:
            for block in iter(lambda: f.read(1 << 22), b""):
                h.update(block)
    return h.hexdigest()


def stamp_file(root: Path, region: str) -> Path:
    return root / "data" / "out" / region / ".rebuild-stamps.json"


def read_stamps(root: Path, region: str) -> dict:
    try:
        return json.loads(stamp_file(root, region).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record(root: Path, region: str, stage: str) -> None:
    """Remember which inputs this stage's outputs were built from."""
    ins = [p for p in inputs(root, region, stage) if p.exists()]
    if not ins:
        return
    st = read_stamps(root, region)
    st[stage] = digest(ins)
    stamp_file(root, region).parent.mkdir(parents=True, exist_ok=True)
    stamp_file(root, region).write_text(json.dumps(st, indent=1), encoding="utf-8")


def own_reason(root: Path, region: str, stage: str) -> str | None:
    """Why this stage is stale on its own account (missing or older than its inputs), or None if it is current."""
    outs = outputs(root, region, stage)
    missing = [p.name for p in outs if not p.exists()]
    if missing:
        return f"missing {', '.join(missing)}"
    if stage == "base":  # vectors rewrites manifest.json without the "base" entry
        if "base" not in json.loads((root / "data" / "out" / region / "manifest.json").read_text(encoding="utf-8")):
            return "manifest.json has no base entry"
    ins = [p for p in inputs(root, region, stage) if p.exists()]
    if not ins:
        return None
    stamp = read_stamps(root, region).get(stage)
    if stamp is not None:
        return None if stamp == digest(ins) else "input changed"
    if newest(ins) > min(p.stat().st_mtime for p in outs):
        return "older than its input (no stamp yet)"
    return None


@dataclass
class Step:
    region: str
    stage: str
    run: bool
    reason: str


def plan(root: Path, regions: list[str], *, force: bool = False, start: str | None = None, only: list[str] | None = None) -> list[Step]:
    """The steps to take, per region in stage order. `start` forces that stage and everything after it; `only` limits the stages."""
    steps: list[Step] = []
    for region in regions:
        will_run: set[str] = set()
        for stage in STAGES:
            if only and stage.name not in only:
                continue
            reason = None
            if force:
                reason = "forced"
            elif start and NAMES.index(stage.name) >= NAMES.index(start):
                reason = f"from {start}"
            else:
                reason = own_reason(root, region, stage.name)
                if reason is None:
                    up = [d for d in stage.deps if d in will_run]
                    reason = f"{up[0]} was rebuilt" if up else None
            if stage.name == "grids" and not force and not start and reason and reason.startswith("missing"):
                reason = "grid missing: " + reason  # blocked: acquired by --download or build_hires.py
            if reason:
                will_run.add(stage.name)
            steps.append(Step(region, stage.name, bool(reason), reason or "current"))
    return steps


def command(stage: str, region: str, download: bool) -> list[str] | None:
    py = sys.executable
    if stage == "grids":
        return [py, str(SCRIPTS / "fetch_data.py"), "--grids", region, "--force"] if download else None
    script = {"render": "render_region.py", "tiles": "build_tiles.py", "vectors": "build.py", "base": "base_tint.py"}[stage]
    return [py, str(SCRIPTS / script), region]


def regions_in_registry(root: Path) -> list[str]:
    reg = json.loads((root / "regions" / "regions.json").read_text(encoding="utf-8"))
    items = reg["regions"] if isinstance(reg, dict) and "regions" in reg else reg
    return [r["id"] for r in items] if isinstance(items, list) else list(items)


def execute(root: Path, steps: list[Step], *, download: bool, runner=subprocess.run, log=print) -> dict[str, str]:
    """Run the stale steps; returns {region: 'ok' | 'blocked: ...' | 'failed: <stage>'}. A failure stops that region only."""
    result: dict[str, str] = {}
    for region in dict.fromkeys(s.region for s in steps):
        result[region] = "ok"
        for s in (x for x in steps if x.region == region and x.run):
            cmd = command(s.stage, region, download)
            if cmd is None:
                result[region] = f"blocked: no grid; use --download (grids-* release) or build_hires.py ({s.reason})"
                log(f"  {region}: {result[region]}")
                break
            log(f"  {region}: {s.stage} ({s.reason}) ...")
            if runner(cmd, cwd=root).returncode != 0:  # build.py reads data/out relative to the repo root
                result[region] = f"failed: {s.stage}"
                log(f"  {region}: {result[region]}")
                break
            record(root, region, s.stage)
    return result


def show(steps: list[Step]) -> None:
    for region in dict.fromkeys(s.region for s in steps):
        line = "  ".join(f"{s.stage}:{'RUN' if s.run else 'ok'}" for s in steps if s.region == region)
        print(f"{region:14s} {line}")
        for s in steps:
            if s.region == region and s.run:
                print(f"{'':14s}   {s.stage}: {s.reason}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "run", "adopt"])
    ap.add_argument("regions", nargs="*")
    ap.add_argument("--force", action="store_true", help="every stage, whether stale or not")
    ap.add_argument("--from", dest="start", choices=NAMES, help="this stage and all later ones")
    ap.add_argument("--only", help="comma-separated stages to consider")
    ap.add_argument("--download", action="store_true", help="restore a missing grid from the latest grids-* release (network)")
    ap.add_argument("--package", action="store_true", help="after a run, pack dist/ with publish_data.py build")
    a = ap.parse_args(argv)
    known = regions_in_registry(ROOT)
    bad = [r for r in a.regions if r not in known]
    if bad:
        print(f"unknown region(s): {', '.join(bad)}; known: {', '.join(known)}")
        return 2
    regions = a.regions or [r for r in known if r not in IN_GIT]
    if a.cmd == "adopt":
        for r in regions:
            for st in NAMES[1:]:
                if all(p.exists() for p in outputs(ROOT, r, st)):  # only stages that have outputs to vouch for
                    record(ROOT, r, st)
            print(f"{r}: recorded stamps for {', '.join(k for k in NAMES[1:] if k in read_stamps(ROOT, r))}")
        return 0
    steps = plan(ROOT, regions, force=a.force, start=a.start, only=a.only.split(",") if a.only else None)
    show(steps)
    if a.cmd == "plan":
        return 0
    result = execute(ROOT, steps, download=a.download)
    bad = {r: v for r, v in result.items() if v != "ok"}
    if a.package and not bad:
        subprocess.run([sys.executable, str(SCRIPTS / "publish_data.py"), "build", *[r for r in regions if r != "vestland"]], cwd=ROOT, check=True)
    print("done" if not bad else "not finished: " + "; ".join(f"{r} {v}" for r, v in bad.items()))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
