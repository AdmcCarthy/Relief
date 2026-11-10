"""Base-map tint for a frame: the Detuned house style rendered once, for every consumer to draw under its data.

Sea floor as a LINEAR gradient on the region's depth scale (shelf 0 to 1,300 m or ocean 0 to 7,000 m, by `bathymetry`
in regions.json); land in STEPPED height classes, cross-blended by climate zone (Beck and others 2023 weights from the
demo texture); both in the light and the dark theme. The stops are the ones in preview/palette.js (tests keep them in step).

Writes data/out/<region>/regional_base_light.png and regional_base_dark.png (RGB, the regional LOD grid, the frame's
extent) and records them in manifest.json under "base". Consumers (Bedrock, source-to-sink, Sand-from-the-Source, Sheet,
SubScout figures) draw that image with an identity transform, their data over it, then the hillshade; they never colour
Relief's bands or heights themselves.

Usage: uv run python scripts/base_tint.py <region> [<region> ...]
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

# Mirrors preview/palette.js (ZPAL, DETUNED_SEA, DETUNED_OCEAN, LB, SB, OCEAN_SB). Change both together.
LB, LMAX = [0, 50, 150, 300, 600, 1000, 1500, 2000], 2000
SB, SMAX = [0, 20, 50, 100, 200, 500, 1000], 1300
OCEAN_SB, OCEAN_MAX = [0, 200, 1000, 2000, 3000, 4000, 5000, 6000, 7000], 7000
ZPAL = {
    "light": {
        "temperate": ["#d6e8b8", "#c6dea0", "#bad38f", "#cbcf92", "#d9c897", "#ccb8a0", "#d8d0c6", "#efece8"],
        "boreal": ["#a9c7a6", "#97bb98", "#8aae8c", "#93a98b", "#a8ad96", "#ccb8a0", "#d8d0c6", "#efece8"],
        "tundra": ["#e0e3dc", "#d6dad2", "#cdd1c9", "#c6c8c0", "#c4c0b6", "#ccb8a0", "#d8d0c6", "#efece8"],
        "arid": ["#efe2c2", "#e9d6ac", "#e1c695", "#d6b382", "#c9a077", "#ccb8a0", "#d8d0c6", "#efece8"],
    },
    "dark": {
        "temperate": ["#46572f", "#4c5d33", "#536237", "#5d633b", "#665f42", "#655d50", "#85807a", "#aaa6a1"],
        "boreal": ["#2c4232", "#304836", "#354d39", "#3f513e", "#4e5547", "#655d50", "#85807a", "#aaa6a1"],
        "tundra": ["#55595a", "#585b5b", "#5b5d5c", "#5e5e5b", "#615d57", "#655d50", "#85807a", "#aaa6a1"],
        "arid": ["#5e533c", "#665a3f", "#6c5c40", "#6e5a43", "#6a5747", "#655d50", "#85807a", "#aaa6a1"],
    },
}
DETUNED_SEA = {
    "light": ["#e8f0f2", "#cfe1e6", "#aacdd8", "#7eb0c5", "#5891ae", "#3a6d94", "#264b73", "#162b50"],
    "dark": ["#3a8aa2", "#2f7690", "#25647d", "#1c526b", "#144157", "#0e3045", "#092336", "#06172a"],
}
DETUNED_OCEAN = {
    "light": ["#e2f4f9", "#bfe2ed", "#83bddc", "#5c9acd", "#4579ba", "#355a9f", "#2a3e80", "#1e2763", "#131546"],
    "dark": ["#71b7c8", "#56a5bd", "#2c83aa", "#1d679c", "#154b8a", "#113375", "#101e5c", "#0a0b42", "#040027"],
}
ZONES = ["temperate", "boreal", "tundra", "arid"]


def rgb(h: str) -> np.ndarray:
    return np.array([int(h[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float32)


def tune(h: str, sat: float, mix: float) -> np.ndarray:
    """palette.js `tune`: saturation towards the colour's own grey, then lifted (mix > 0) or sunk (mix < 0)."""
    c = rgb(h)
    y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    t = 255.0 if mix > 0 else 0.0
    g = y + (c - y) * sat
    return np.clip(g + (t - g) * abs(mix), 0, 255)


def linear_ramp(t: np.ndarray, breaks: list[float], cols: list[str], vmax: float) -> np.ndarray:
    """palette.js `at` + `rampAt`: piecewise-linear interpolation between the stops, t in 0..1."""
    pos = [b / vmax for b in breaks] + ([1.0] if len(cols) > len(breaks) else [])
    colours = np.stack([rgb(c) for c in cols])
    out = np.zeros(t.shape + (3,), dtype=np.float32)
    t = np.clip(t, 0, 1)
    for k in range(len(pos) - 1):
        t0, t1 = pos[k], pos[k + 1]
        m = (t >= t0) & (t <= t1) if k == len(pos) - 2 else (t >= t0) & (t < t1)
        f = ((t[m] - t0) / (t1 - t0 or 1))[:, None]
        out[m] = colours[k] * (1 - f) + colours[k + 1] * f
    return out


def stepped_land(z: np.ndarray, weights: np.ndarray, theme: str) -> np.ndarray:
    """Stepped height classes; each class colour is the zone ramps at half saturation, blended by the zone weights."""
    cls = np.clip(np.searchsorted(np.array(LB[1:], dtype=np.float32), z, side="right"), 0, len(LB) - 1)
    out = np.zeros(z.shape + (3,), dtype=np.float32)
    for zi, zone in enumerate(ZONES):
        cols = np.stack([tune(c, 0.5, 0.08 if theme == "light" else -0.08) for c in ZPAL[theme][zone]])
        out += weights[..., zi : zi + 1] * cols[cls]
    return out


def zone_weights(path: Path, shape: tuple[int, int]) -> np.ndarray:
    """Temperate, boreal, tundra weights from zones.png (R, G, B); arid is the remainder."""
    im = Image.open(path).convert("RGB").resize((shape[1], shape[0]), Image.BILINEAR)
    w = np.asarray(im, dtype=np.float32) / 255.0
    arid = np.clip(1.0 - w.sum(axis=-1), 0, 1)
    w = np.dstack([w, arid])
    s = w.sum(axis=-1, keepdims=True)
    s[s == 0] = 1
    return w / s


def elevation(demo: Path, shape: tuple[int, int]) -> np.ndarray:
    meta = json.loads((demo / "meta.json").read_text(encoding="utf-8"))
    base, step = meta["encoding"]["base"], meta["encoding"]["step"]
    a = np.asarray(Image.open(io.BytesIO((demo / "elev.webp").read_bytes())).convert("RGB")).astype("uint32")
    z = (base + ((a[..., 0] << 8) | a[..., 1]) * step).astype(np.float32)
    return np.asarray(Image.fromarray(z, "F").resize((shape[1], shape[0]), Image.BOX), dtype=np.float32)


def render(region: str) -> dict:
    out = ROOT / "data" / "out" / region
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    regions = json.loads((ROOT / "regions" / "regions.json").read_text(encoding="utf-8"))["regions"]
    bathy = next((r.get("bathymetry", "shelf") for r in regions if r["id"] == region), "shelf")
    h, w = manifest["lods"]["regional"]["shape"]
    z = elevation(out / "demo", (h, w))
    weights = zone_weights(out / "demo" / "zones.png", (h, w))
    sea = z < 0
    files = {}
    for theme in ("light", "dark"):
        if bathy == "ocean":
            s = linear_ramp(-z / OCEAN_MAX, OCEAN_SB, DETUNED_OCEAN[theme], OCEAN_MAX)
        else:
            s = linear_ramp(-z / SMAX, SB, DETUNED_SEA[theme], SMAX)
        land = stepped_land(np.maximum(z, 0), weights, theme)
        img = np.where(sea[..., None], s, land)
        name = f"regional_base_{theme}.png"
        Image.fromarray(np.round(np.clip(img, 0, 255)).astype("uint8"), "RGB").save(out / name, optimize=True)
        files[theme] = name
    manifest["base"] = {
        "regional": files,
        "style": f"Detuned: linear bathymetry on the {bathy} depth scale, stepped land classes cross-blended by climate zone",
        "depth_scale": {"kind": bathy, "max_m": OCEAN_MAX if bathy == "ocean" else SMAX, "ticks_m": [0, 1000, 2000, 3000, 4000, 5000, 6000] if bathy == "ocean" else [0, 250, 500, 1000]},
        "land_classes_m": LB,
        "note": "Draw this image with an identity transform in the frame extent, your data over it, then the hillshade. Do not recolour bands or heights.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return {"region": region, "shape": [h, w], "bathymetry": bathy, "sea_share": round(float(sea.mean()), 3), "files": files}


if __name__ == "__main__":
    for r in sys.argv[1:] or ["ne_europe"]:
        print(render(r))
