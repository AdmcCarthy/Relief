"""Line simplification and smoothing for the visual contour layer.

Filtering (keeps a subset of the original points):
- douglas_peucker: keeps the points that matter most for shape (Douglas & Peucker 1973); good at minimal
  simplification, poor at caricature. shapely's simplify implements it.
- visvalingam: removes the point whose triangle with its neighbours has the smallest area, repeatedly
  (Visvalingam & Whyatt 1993); removes trivial wiggles first, which reads more naturally at small scales.
Smoothing (fits new points):
- chaikin: corner cutting (Chaikin 1974); each pass replaces every corner with points at 1/4 and 3/4 along
  its edges; converges to a quadratic B-spline that stays inside the original polygon's convex hull.
- catmull_rom: centripetal Catmull-Rom spline (alpha 0.5) through the points; passes through every kept
  point, and the centripetal form avoids cusps and self-intersections within segments (Yuksel et al. 2011).
"""

from __future__ import annotations

import heapq

import numpy as np


def douglas_peucker(pts: np.ndarray, tol: float) -> np.ndarray:
    from shapely.geometry import LineString

    closed = np.allclose(pts[0], pts[-1])
    out = np.asarray(LineString(pts).simplify(tol, preserve_topology=True).coords)  # no new self-crossings
    if closed and not np.allclose(out[0], out[-1]):
        out = np.vstack([out, out[:1]])
    return out


def visvalingam(pts: np.ndarray, min_area: float) -> np.ndarray:
    """Remove points whose effective triangle area is below min_area (closed rings keep >= 4 points)."""
    closed = np.allclose(pts[0], pts[-1])
    p = pts[:-1] if closed else pts
    n = len(p)
    if n < 5:
        return pts
    prev = list(range(-1, n - 1)); nxt = list(range(1, n + 1))
    if closed:
        prev[0] = n - 1; nxt[-1] = 0
    alive = [True] * n

    def area(i):
        a, b = prev[i], nxt[i]
        if a < 0 or b >= n:
            return np.inf
        (x1, y1), (x2, y2), (x3, y3) = p[a], p[i], p[b]
        return abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)) / 2

    heap = [(area(i), i) for i in range(n)]
    heapq.heapify(heap)
    left = n
    while heap and left > (4 if closed else 2):
        ar, i = heapq.heappop(heap)
        if not alive[i] or ar != area(i):
            continue
        if ar >= min_area:
            break
        alive[i] = False; left -= 1
        a, b = prev[i], nxt[i]
        if a >= 0: nxt[a] = b
        if b < n: prev[b] = a
        for j in (a, b):
            if 0 <= j < n and alive[j]:
                heapq.heappush(heap, (area(j), j))
    q = p[np.array(alive)]
    return np.vstack([q, q[:1]]) if closed else q


def chaikin(pts: np.ndarray, iterations: int = 2) -> np.ndarray:
    closed = np.allclose(pts[0], pts[-1])
    p = pts[:-1] if closed else pts
    for _ in range(iterations):
        if closed:
            a, b = p, np.roll(p, -1, axis=0)
        else:
            a, b = p[:-1], p[1:]
        q = np.empty((2 * len(a), 2))
        q[0::2] = 0.75 * a + 0.25 * b
        q[1::2] = 0.25 * a + 0.75 * b
        p = q if closed else np.vstack([pts[:1], q, pts[-1:]])
    return np.vstack([p, p[:1]]) if closed else p


def catmull_rom(pts: np.ndarray, samples: int = 4, alpha: float = 0.5) -> np.ndarray:
    """Centripetal Catmull-Rom through the points, `samples` points per segment."""
    closed = np.allclose(pts[0], pts[-1])
    p = pts[:-1] if closed else pts
    n = len(p)
    if n < 3:
        return pts
    ext = np.vstack([p[-1:], p, p[:2]]) if closed else np.vstack([2 * p[:1] - p[1:2], p, 2 * p[-1:] - p[-2:-1]])
    out = []
    segs = n if closed else n - 1
    for i in range(segs):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        t0 = 0.0
        t1 = t0 + max(np.linalg.norm(p1 - p0), 1e-9) ** alpha
        t2 = t1 + max(np.linalg.norm(p2 - p1), 1e-9) ** alpha
        t3 = t2 + max(np.linalg.norm(p3 - p2), 1e-9) ** alpha
        for t in np.linspace(t1, t2, samples, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out = np.array(out)
    return np.vstack([out, out[:1]]) if closed else np.vstack([out, p[-1:]])
