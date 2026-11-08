"""Region registry: load, derive and check the named map regions in regions/regions.json.

Other apps can read regions/regions.json (published at <Pages>/regions/regions.json) without any Python.
Within Relief, `scripts/areas.py` exposes the same data as AREAS.

  python scripts/regions.py sync    # derive extent / bbox / size from 'design'; write outlines + proj4 strings
  python scripts/regions.py check   # coverage against Sodir blocks and fields and EMODnet wells -> coverage.json
  python scripts/regions.py show    # one line per region
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, box, shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "regions"
RAW = ROOT / "data" / "raw" / "regions"
LONLAT = "EPSG:4326"
EDGE_N = 200  # points per edge when projecting a lon/lat box or unprojecting an extent


def load(path: Path = REG / "regions.json") -> dict:
    return json.loads(path.read_text())


def crs_of(region: dict) -> CRS:
    return CRS.from_user_input(region["crs"]["code"])


def _densify(x0: float, y0: float, x1: float, y1: float, n: int = EDGE_N) -> np.ndarray:
    k = np.linspace(0, 1, n)
    return np.vstack([np.column_stack([x0 + (x1 - x0) * k, np.full(n, y0)]), np.column_stack([np.full(n, x1), y0 + (y1 - y0) * k]),
                      np.column_stack([x1 + (x0 - x1) * k, np.full(n, y1)]), np.column_stack([np.full(n, x0), y1 + (y0 - y1) * k])])


def derive_extent(region: dict) -> list[float]:
    """Projected rectangle (x0, y0, x1, y1) for the region's design, in the region CRS."""
    d, crs = region["design"], crs_of(region)
    fwd = Transformer.from_crs(LONLAT, crs, always_xy=True)
    if d.get("world"):
        xs = [fwd.transform(lon, 0)[0] for lon in (-180, 180)]
        ys = [fwd.transform(0, lat)[1] for lat in (-90, 90)]
        return [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))]
    if "lonlat_box" in d:
        w, s, e, n = d["lonlat_box"]
        edge = _densify(w, s, e, n)
        px, py = fwd.transform(edge[:, 0], edge[:, 1])
        px, py = np.asarray(px), np.asarray(py)
        if d["fit"] == "inner":  # largest upright rectangle inside the projected box: no tilted edges
            m = len(edge) // 4
            left, right, bottom, top = (slice(3 * m, 4 * m), slice(m, 2 * m), slice(0, m), slice(2 * m, 3 * m))
            return [float(px[left].max()), float(py[bottom].max()), float(px[right].min()), float(py[top].min())]
    else:
        px, py = fwd.transform([p[0] for p in d["points"]], [p[1] for p in d["points"]])
    r, margin = d.get("round_m", 10000), d.get("margin_m", 0)
    ext = [float(np.floor((np.min(px) - margin) / r) * r), float(np.floor((np.min(py) - margin) / r) * r),
           float(np.ceil((np.max(px) + margin) / r) * r), float(np.ceil((np.max(py) + margin) / r) * r)]
    if "north_at" in d:  # a rectangle cannot follow a curved parallel: pin the north edge to it at one longitude
        lat, lon = d["north_at"]
        ext[3] = float(np.round(fwd.transform(lon, lat)[1] / r) * r)
    return ext


def derive_bbox(region: dict) -> list[float]:
    """Lon/lat bounds that contain the extent (and the design box, when it has one)."""
    if region["design"].get("world"):
        return [-180.0, -90.0, 180.0, 90.0]
    x0, y0, x1, y1 = region["extent"]
    inv = Transformer.from_crs(crs_of(region), LONLAT, always_xy=True)
    edge = _densify(x0, y0, x1, y1)
    lon, lat = inv.transform(edge[:, 0], edge[:, 1])
    w, s, e, n = float(np.min(lon)), float(np.min(lat)), float(np.max(lon)), float(np.max(lat))
    if "lonlat_box" in region["design"] and region["design"]["fit"] == "inner":
        return list(region["design"]["lonlat_box"])
    return [round(w - 0.01, 3), round(s - 0.01, 3), round(e + 0.01, 3), round(min(n + 0.01, 90.0), 3)]


def outline(region: dict, n: int = 60) -> Polygon:
    """The extent drawn on a lon/lat map: edges densified so that curved projected edges stay curved."""
    if region["design"].get("world"):  # the corners of the frame lie outside the globe
        return box(-180, -90, 180, 90)
    x0, y0, x1, y1 = region["extent"]
    inv = Transformer.from_crs(crs_of(region), LONLAT, always_xy=True)
    pts = _densify(x0, y0, x1, y1, n)
    lon, lat = inv.transform(pts[:, 0], pts[:, 1])
    return Polygon(np.column_stack([np.round(lon, 4), np.round(lat, 4)]))


def sync() -> None:
    reg = load()
    feats = []
    for r in reg["regions"]:
        r["extent"] = [round(v) for v in derive_extent(r)]
        r["bbox"] = derive_bbox(r)
        x0, y0, x1, y1 = r["extent"]
        r["size_km"] = [round((x1 - x0) / 1000), round((y1 - y0) / 1000)]
        r["built"] = (ROOT / "data" / "out" / r["id"] / "manifest.json").exists()  # layers committed under data/out
        crs = crs_of(r)
        r["crs"]["proj4"] = crs.to_proj4() or ""
        r["crs"]["epsg"] = crs.to_epsg()
        feats.append({"type": "Feature", "properties": {"id": r["id"], "name": r["name"], "crs": r["crs"]["code"]},
                      "geometry": json.loads(json.dumps(outline(r).__geo_interface__))})
    (REG / "regions.json").write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
    (REG / "regions.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    show()


def show() -> None:
    for r in load()["regions"]:
        print(f"{r['id']:14s} {r['size_km'][0]:>6,} x {r['size_km'][1]:>6,} km  bbox {r['bbox']}  {r['crs']['name']}")


def _feats(name: str) -> list[dict]:
    return [f for f in json.loads((RAW / f"{name}.geojson").read_text())["features"] if f.get("geometry")]


def check() -> None:
    """Share of Sodir blocks, fields and EMODnet wells inside each region, and of unwanted ones that leak in."""
    reg = load()
    blocks, fields = _feats("sodir_blocks"), _feats("sodir_fields")
    wells = _feats("emodnet_hydrocarbons")
    report: dict = {}
    for r in reg["regions"]:
        cov = r.get("coverage")
        if not cov:
            continue
        fwd = Transformer.from_crs(LONLAT, crs_of(r), always_xy=True)
        frame = box(*r["extent"])
        out: dict = {}
        for key, feats, area_key in (("sodir_blocks", blocks, "blcMainArea"), ("sodir_fields", fields, "fldMainArea")):
            spec = cov.get(key)
            if not spec:
                continue
            groups: dict[str, dict] = {}
            for f in feats:
                g = shp_transform(fwd.transform, shape(f["geometry"]))
                a = f["properties"][area_key].lower()
                s = groups.setdefault(a, {"total": 0, "inside": 0, "touching": 0, "area_inside": 0.0, "area_total": 0.0})
                s["total"] += 1
                s["area_total"] += g.area
                s["inside"] += int(frame.contains(g))
                s["touching"] += int(frame.intersects(g))
                s["area_inside"] += g.intersection(frame).area
            for a, s in groups.items():
                s["share_inside"] = round(s["inside"] / s["total"], 4)
                s["share_area_inside"] = round(s["area_inside"] / s["area_total"], 4)
                del s["area_inside"], s["area_total"]
            for a, s in groups.items():
                if a in [x.lower() for x in spec.get("include", [])]:
                    s["role"] = "wanted"
                elif a in [x.lower() for x in spec.get("exclude", [])]:
                    s["role"] = "unwanted"
            out[key] = groups
        spec = cov.get("wells")
        if spec:
            by: dict[str, list] = {}
            for f in wells:
                if f["properties"]["country"] in spec["countries"]:
                    c = f["geometry"]["coordinates"]
                    if np.isfinite(c[0]) and np.isfinite(c[1]):
                        by.setdefault(f["properties"]["country"], []).append(c[:2])
            w = {}
            for country, pts in by.items():
                x, y = fwd.transform(np.array(pts)[:, 0], np.array(pts)[:, 1])
                x, y = np.asarray(x), np.asarray(y)
                x0, y0, x1, y1 = r["extent"]
                inside = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
                w[country] = {"total": len(pts), "inside": int(inside.sum()), "share_inside": round(float(inside.mean()), 4)}
            out["wells"] = w
        report[r["id"]] = out
    (REG / "coverage.json").write_text(json.dumps(report, indent=1) + "\n")
    for rid, out in report.items():
        print(rid)
        for key, groups in out.items():
            for a, s in groups.items():
                print(f"  {key:13s} {a:14s} {s['inside']:>5}/{s['total']:<5} fully inside ({s['share_inside']:.1%}), area inside {s.get('share_area_inside', 0):.1%}, touching {s.get('touching', '-')}")


if __name__ == "__main__":
    {"sync": sync, "check": check, "show": show}[sys.argv[1] if len(sys.argv) > 1 else "show"]()
