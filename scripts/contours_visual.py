"""Visual contour layer: contours traced from the combined 50 m surface, then simplified and smoothed for
looks rather than survey precision. The precise grid (elev.webp) stays the record; this layer is for drawing.

Pipeline per method, for an 18 x 18 km crop of the Bergen comparison window (50 m cells):
  raw            marching squares on the grid (contourpy), no change
  dp             Douglas-Peucker, tolerance 1 cell
  vw             Visvalingam-Whyatt, minimum triangle area 4 cell^2
  dp_chaikin     Douglas-Peucker (1.5 cells) then 3 passes of Chaikin corner cutting
  vw_catmull     Visvalingam-Whyatt (6 cell^2) then centripetal Catmull-Rom, 4 points per segment
  blur_chaikin   Gaussian pre-blur of the grid (1 cell), DP (1.5 cells), 2 Chaikin passes  <- recommended
Each output reports points, bytes and rings that self-intersect after processing.
Levels follow the stepped scheme: sea 20, 50, 100, 200, 500 m deep; land 50, 150, 300, 600 m.

Usage: python scripts/contours_visual.py <area>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import contourpy
import numpy as np
import smooth
from PIL import Image
from scipy.ndimage import gaussian_filter
from shapely.geometry import LinearRing, LineString

SEA = [20, 50, 100, 200, 500]
LAND = [50, 150, 300, 600]


def decode(path: Path, meta: dict) -> np.ndarray:
    e = np.array(Image.open(path)).astype("float64")
    return meta["encoding"]["base"] + (e[..., 0] * 256 + e[..., 1]) * meta["encoding"]["step"]


def trace(z: np.ndarray, level: float) -> list[np.ndarray]:
    gen = contourpy.contour_generator(z=z, line_type=contourpy.LineType.Separate)
    return [ln for ln in gen.lines(level) if len(ln) >= 4]


METHODS = {
    "raw": lambda ln, c: ln,
    "dp": lambda ln, c: smooth.douglas_peucker(ln, 1.0),
    "vw": lambda ln, c: smooth.visvalingam(ln, 4.0),
    "dp_chaikin": lambda ln, c: smooth.chaikin(smooth.douglas_peucker(ln, 1.5), 3),
    "vw_catmull": lambda ln, c: smooth.catmull_rom(smooth.visvalingam(ln, 6.0), 4),
    "blur_chaikin": lambda ln, c: smooth.chaikin(smooth.douglas_peucker(ln, 1.5), 2),
}


def run(z: np.ndarray, cell: float, min_len_cells: float = 8) -> dict:
    zb = gaussian_filter(z, 1.0)
    out = {}
    for name, fn in METHODS.items():
        src = zb if name == "blur_chaikin" else z
        feats, npts, bad = [], 0, 0
        for kind, levels, sign in (("sea", SEA, -1), ("land", LAND, 1)):
            for lv in levels:
                for ln in trace(src * sign, lv):
                    if LineString(ln).length < min_len_cells:  # drop specks under ~8 cells of line
                        continue
                    q = fn(ln, cell)
                    if len(q) < 3:
                        continue
                    closed = np.allclose(q[0], q[-1]) and len(q) >= 4
                    if closed and not LinearRing(q).is_simple:
                        bad += 1
                    npts += len(q)
                    feats.append({"k": kind, "l": lv, "c": np.round(q * 4).astype(int).ravel().tolist()})  # quarter-cell integers
        txt = json.dumps(feats, separators=(",", ":"))
        out[name] = {"lines": feats, "points": npts, "bytes": len(txt), "self_intersecting_rings": bad, "count": len(feats)}
    return out


def main(area: str) -> None:
    d = Path("data/out") / area / "demo"
    meta = json.loads((d / "meta.json").read_text())
    z = decode(d / "compare" / "kartverket50.webp", meta)
    n = z.shape[0]
    z = z[n // 4: 3 * n // 4, n // 4: 3 * n // 4]  # central 18 x 18 km
    res = run(z, meta["compare"]["cell"])
    (d / "contours_visual.json").write_text(json.dumps({"size": [z.shape[1], z.shape[0]], "sea": SEA, "land": LAND,
        "methods": {k: {kk: vv for kk, vv in v.items()} for k, v in res.items()}}, separators=(",", ":")))
    for k, v in res.items():
        print(f"{k:13s} lines {v['count']:5d}  points {v['points']:7d}  {v['bytes'] / 1e3:7.0f} KB  self-intersecting rings {v['self_intersecting_rings']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "vestland")
