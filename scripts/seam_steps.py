"""Depth step across source boundaries in a built hires grid (derived measure; see docs/hires-sources.md).

For each pair of sea sources that touch, the absolute elevation difference between neighbouring cells that belong to
different sources, in water deeper than MIN_DEPTH. Reads data/raw/<region>/hires.tif and hires_sources.png.

    python scripts/seam_steps.py north_sea norwegian_sea
"""
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from scipy.ndimage import binary_dilation

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
MIN_DEPTH = 200  # m: shallower water is dominated by real relief at the coast
MIN_EDGE_PX = 2000
NEAR_CELLS = 6  # the control sample: same-source neighbours within this many cells of any source boundary


def source_ids(src: np.ndarray, sea: np.ndarray, shares: dict) -> dict:
    """Map pixel values in hires_sources.png to source ids by matching each value's share of the sea to hires.json."""
    have = {int(v): float(((src == v) & sea).sum() / max(sea.sum(), 1)) for v in np.unique(src)}
    ids = {}
    for sid, f in shares.items():
        ids[min(have, key=lambda v: abs(have[v] - f))] = sid
    return ids


def steps(region: str) -> tuple[list[tuple[str, str, int, float, float]], float]:
    z = rasterio.open(RAW / region / "hires.tif").read(1).astype("float32")
    src = np.array(Image.open(RAW / region / "hires_sources.png"))
    meta = json.load(open(RAW / region / "hires.json"))
    ids = source_ids(src, (z < 0) & np.isfinite(z), meta["sea_share_by_source"]["sea"])
    acc: dict = {}
    control = []
    seam = np.zeros(z.shape, bool)
    seam[:, :-1] |= src[:, :-1] != src[:, 1:]
    seam[:-1, :] |= src[:-1, :] != src[1:, :]
    near = binary_dilation(seam, iterations=NEAR_CELLS)
    for dx, dy in ((1, 0), (0, 1)):
        a, b = z[: z.shape[0] - dy, : z.shape[1] - dx], z[dy:, dx:]
        sa, sb = src[: src.shape[0] - dy, : src.shape[1] - dx], src[dy:, dx:]
        nb = near[: z.shape[0] - dy, : z.shape[1] - dx]
        same = (sa == sb) & nb & (a < -MIN_DEPTH) & (b < -MIN_DEPTH) & np.isfinite(a) & np.isfinite(b)
        control.append(np.abs(a[same] - b[same]))
        ok = (sa != sb) & (a < -MIN_DEPTH) & (b < -MIN_DEPTH) & np.isfinite(a) & np.isfinite(b)
        for pa, pb in set(zip(sa[ok].tolist(), sb[ok].tolist())):
            if pa not in ids or pb not in ids:
                continue  # land or unmapped value
            d = np.abs(a[ok & (sa == pa) & (sb == pb)] - b[ok & (sa == pa) & (sb == pb)])
            acc.setdefault(tuple(sorted((ids[pa], ids[pb]))), []).append(d)
    out = []
    for (x, y), parts in acc.items():
        d = np.concatenate(parts)
        if d.size >= MIN_EDGE_PX:
            out.append((x, y, int(d.size), float(np.median(d)), float(np.percentile(d, 90))))
    return sorted(out, key=lambda r: -r[2]), float(np.median(np.concatenate(control)))


if __name__ == "__main__":
    for region in sys.argv[1:]:
        rows, base = steps(region)
        print(f"== {region}: step across a source boundary in water deeper than {MIN_DEPTH} m")
        print(f"   control: median step between same-source neighbours within {NEAR_CELLS} cells of a boundary = {base:.1f} m (slope alone)")
        for x, y, n, med, p90 in rows:
            print(f"  {x:>20} | {y:<20} edge cells {n:7d}  median {med:5.1f} m  p90 {p90:6.1f} m  excess {med - base:+5.1f} m")
