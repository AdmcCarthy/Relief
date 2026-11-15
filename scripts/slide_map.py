"""Slide map: one country cut out of Relief's terrain, for slides and summary displays.

Mainland Norway alone: the sky shade (docs/sky-view.md) on a very subdued, nearly transparent fill, the country's
outline, and its major cities. Everything outside the country is transparent, so the picture sits on any slide
background; the shade is carried as ink (dark in the hollows, light on the lit slopes) rather than as a colour, so it
reads on light and dark slides alike. Two variants differ only in the ink of the outline and labels.

    python scripts/slide_map.py norway [--scale 2]

Writes data/out/<region>/slide_<region>_{light,dark}.png (RGBA), slide_<region>.svg (outline, cities and labels as
editable vectors over the light PNG) and slide_<region>.json (frame, pixel positions, sources, attribution).

Terrain: the region's own merged grid when built (data/raw/<region>/hires.tif), else the Europe frame's grid
(data/raw/europe_s2s/hires.tif, 1,600 m) warped into the frame: coarse but honest at slide scale. Country outline and
city positions: Natural Earth 10 m (public domain, scripts/fetch_natural_earth.py); the coast is traced from the terrain
so fjords are the terrain's, and the land border is Natural Earth's.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
import shapely
from areas import AREAS
from fetch_natural_earth import ATTRIBUTION as NE_ATTRIBUTION
from fetch_natural_earth import ensure as ensure_natural_earth
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize, shapes
from rasterio.warp import reproject
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union
from sky_view import sky_hillshade

ROOT = Path(__file__).resolve().parents[1]
FALLBACK_GRID = "europe_s2s"  # the frame whose merged grid stands in until the region is built from its own sources

COUNTRY = {"norway": {"admin": "Norway", "cities": ["Oslo", "Bergen", "Trondheim", "Stavanger", "Harstad"],
                      "keep": lambda lon, lat: lon > 0 and 55 < lat < 72}}  # mainland and its islands: not Svalbard, Jan Mayen, Bouvet
LABEL_SIDE = {"Oslo": "right", "Bergen": "right", "Trondheim": "right", "Stavanger": "right", "Harstad": "right"}  # all inland: a label west of the coast would leave the picture

INK = {"light": {"line": (43, 58, 68), "text": (31, 42, 51), "fill": (233, 237, 228), "fill_alpha": 0.32},
       "dark": {"line": (230, 237, 242), "text": (236, 241, 245), "fill": (185, 196, 184), "fill_alpha": 0.22}}
SHADOW_INK, SHADOW_MAX = (20, 28, 36), 0.62  # the hollows: dark ink, strongest where the sky shade is darkest
LIGHT_INK, LIGHT_MAX = (255, 255, 255), 0.45  # the lit slopes: white ink
FONT = Path("C:/Windows/Fonts/segoeui.ttf")


# ---------------------------------------------------------------------------------------------- terrain
def terrain(region: str, cell: float) -> tuple[np.ndarray, rasterio.Affine, dict]:
    """Heights on the frame at `cell` metres: the region's own grid when built, else the fallback frame's grid warped in."""
    a = AREAS[region]
    x0, y0, x1, y1 = a["extent"]
    w, h = math.ceil((x1 - x0) / cell), math.ceil((y1 - y0) / cell)
    tr = rasterio.Affine(cell, 0, x0, 0, -cell, y1)
    own = ROOT / "data" / "raw" / region / "hires.tif"
    src_dir = region if own.exists() else FALLBACK_GRID
    path = ROOT / "data" / "raw" / src_dir / "hires.tif"
    meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    z = np.full((h, w), np.nan, dtype="float32")
    with rasterio.open(path) as s:
        res = Resampling.average if cell >= s.res[0] * 1.2 else Resampling.bilinear
        reproject(rasterio.band(s, 1), z, dst_transform=tr, dst_crs=a["crs"], dst_nodata=np.nan, resampling=res, tolerance=0.0)
    src = {"grid": src_dir, "cell_m": meta["cell_m"], "built": meta.get("built"), "attribution": meta.get("attribution", []),
           "note": "the region's own grid" if src_dir == region else f"warped from the {src_dir} frame's grid until this region is built"}
    return np.nan_to_num(z, nan=0.0), tr, src


# ---------------------------------------------------------------------------------------------- country
def country_polygon(region: str, crs: str) -> MultiPolygon:
    ne = ensure_natural_earth()
    spec = COUNTRY[region]
    fc = json.loads((ne / "ne_10m_admin_0_countries.geojson").read_text(encoding="utf-8"))
    feat = next(f for f in fc["features"] if f["properties"].get("ADMIN") == spec["admin"])
    geom = shape(feat["geometry"])
    parts = [p for p in getattr(geom, "geoms", [geom]) if spec["keep"](*p.representative_point().coords[0])]
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    project = lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1]))
    return MultiPolygon([shapely.transform(p, project) for p in parts])


def cities(region: str, crs: str) -> list[dict]:
    ne = ensure_natural_earth()
    spec = COUNTRY[region]
    fc = json.loads((ne / "ne_10m_populated_places_simple.geojson").read_text(encoding="utf-8"))
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    out = []
    for f in fc["features"]:
        p = f["properties"]
        if p.get("adm0name") == spec["admin"] and p.get("name") in spec["cities"]:
            lon, lat = f["geometry"]["coordinates"]
            x, y = t.transform(lon, lat)
            out.append({"name": p["name"], "lon": lon, "lat": lat, "x": x, "y": y, "pop_max": p.get("pop_max")})
    missing = set(spec["cities"]) - {c["name"] for c in out}
    if missing:
        raise SystemExit(f"cities not in Natural Earth populated places: {sorted(missing)}")
    return sorted(out, key=lambda c: -c["y"])


def country_mask(poly: MultiPolygon, z: np.ndarray, tr: rasterio.Affine, cell: float) -> np.ndarray:
    """Inside the country and above the sea: the land border is Natural Earth's (buffered a few cells so its generalised line
    does not clip the terrain), the coast is the terrain's own 0 m line."""
    inside = rasterize([(poly.buffer(3 * cell), 1)], out_shape=z.shape, transform=tr, fill=0, dtype="uint8").astype(bool)
    return inside & (z > 0)


def outline(mask: np.ndarray, tr: rasterio.Affine, cell: float, min_cells: int = 12) -> list[Polygon]:
    polys = [shape(g) for g, v in shapes(mask.astype("uint8"), mask=mask, transform=tr) if v == 1]
    keep = [p.simplify(cell * 0.6, preserve_topology=True) for p in polys if p.area >= min_cells * cell * cell]
    u = unary_union(keep)
    return [p for p in getattr(u, "geoms", [u]) if not p.is_empty]


# ---------------------------------------------------------------------------------------------- picture
def over(rgb: np.ndarray, alpha: np.ndarray, ink: tuple, a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Source-over of a constant-colour ink with per-pixel alpha `a` onto straight-alpha (rgb, alpha)."""
    a = a[..., None]
    out_alpha = a + alpha[..., None] * (1 - a)
    col = np.array(ink, dtype=np.float32) / 255
    out_rgb = np.where(out_alpha > 0, (col * a + rgb * alpha[..., None] * (1 - a)) / np.maximum(out_alpha, 1e-6), 0)
    return out_rgb, out_alpha[..., 0]


def picture(z: np.ndarray, mask: np.ndarray, cell: float, theme: str, scale: int) -> Image.Image:
    ink = INK[theme]
    shade = sky_hillshade(z, cell)
    h, w = z.shape
    rgb = np.zeros((h, w, 3), dtype=np.float32) + np.array(ink["fill"], dtype=np.float32) / 255
    alpha = np.full((h, w), ink["fill_alpha"], dtype=np.float32)
    rgb, alpha = over(rgb, alpha, SHADOW_INK, np.clip(1 - shade, 0, 1) * SHADOW_MAX)
    rgb, alpha = over(rgb, alpha, LIGHT_INK, np.clip(shade - 1, 0, 1) * LIGHT_MAX)
    img = Image.fromarray(np.dstack([np.clip(rgb * 255, 0, 255), np.clip(alpha * 255, 0, 255)]).astype("uint8"), "RGBA")
    m = Image.fromarray((mask * 255).astype("uint8"), "L")
    if scale > 1:
        img = img.resize((w * scale, h * scale), Image.BICUBIC)
        m = m.resize((w * scale, h * scale), Image.BILINEAR)
    m = m.filter(ImageFilter.GaussianBlur(0.6 * scale))  # a soft edge, not a staircase of cells
    a = np.asarray(img)[..., 3].astype(np.float32) * (np.asarray(m, dtype=np.float32) / 255)
    out = np.asarray(img).copy()
    out[..., 3] = np.clip(a, 0, 255).astype("uint8")
    out[out[..., 3] == 0, :3] = ink["fill"]  # the colour under fully transparent pixels: the fill, so edges never fringe dark
    return Image.fromarray(out, "RGBA")


def crop_to(mask: np.ndarray, margin: int) -> tuple[slice, slice]:
    """Rows and columns that hold the country, plus a margin of cells for the sky search and the labels."""
    rows, cols = np.where(mask.any(axis=1))[0], np.where(mask.any(axis=0))[0]
    r0, r1 = max(0, rows[0] - margin), min(mask.shape[0], rows[-1] + margin + 1)
    c0, c1 = max(0, cols[0] - margin), min(mask.shape[1], cols[-1] + margin + 1)
    return slice(r0, r1), slice(c0, c1)


def px(tr: rasterio.Affine, x: float, y: float, scale: int) -> tuple[float, float]:
    c, r = ~tr * (x, y)
    return c * scale, r * scale


def draw_vectors(img: Image.Image, polys: list[Polygon], towns: list[dict], tr: rasterio.Affine, theme: str, scale: int) -> Image.Image:
    ink = INK[theme]
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lw = max(1, round(1.6 * scale))
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            pts = [px(tr, x, y, scale) for x, y in ring.coords]
            d.line(pts, fill=(*ink["line"], 190), width=lw, joint="curve")
    font = ImageFont.truetype(str(FONT), size=round(22 * scale))
    r = 5.5 * scale
    for c in towns:
        x, y = px(tr, c["x"], c["y"], scale)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*ink["text"], 255), outline=(255, 255, 255, 230), width=max(1, round(1.5 * scale)))
        side = LABEL_SIDE.get(c["name"], "right")
        gap = 11 * scale
        anchor = "lm" if side == "right" else "rm"
        tx = x + gap if side == "right" else x - gap
        d.text((tx, y), c["name"], font=font, fill=(*ink["text"], 255), anchor=anchor,
               stroke_width=round(2.2 * scale), stroke_fill=(255, 255, 255, 170) if theme == "light" else (20, 28, 36, 170))
    return Image.alpha_composite(img, layer)


def svg(path: Path, png_name: str, size: tuple[int, int], polys: list[Polygon], towns: list[dict], tr: rasterio.Affine, scale: int) -> None:
    ink = INK["light"]
    w, h = size
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             f'<image xlink:href="{png_name}" width="{w}" height="{h}"/>',
             f'<g id="outline" fill="none" stroke="rgb({ink["line"][0]},{ink["line"][1]},{ink["line"][2]})" stroke-opacity="0.75" stroke-width="{1.6 * scale:g}" stroke-linejoin="round">']
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            parts.append('<path d="M' + " L".join(f"{x:.1f} {y:.1f}" for x, y in (px(tr, cx, cy, scale) for cx, cy in ring.coords)) + ' Z"/>')
    parts.append("</g>")
    parts.append(f'<g id="cities" font-family="Segoe UI, Instrument Sans, Arial, sans-serif" font-size="{22 * scale}" fill="rgb({ink["text"][0]},{ink["text"][1]},{ink["text"][2]})">')
    for c in towns:
        x, y = px(tr, c["x"], c["y"], scale)
        side = LABEL_SIDE.get(c["name"], "right")
        tx, anchor = (x + 11 * scale, "start") if side == "right" else (x - 11 * scale, "end")
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{5.5 * scale}" stroke="white" stroke-width="{1.5 * scale}"/>')
        parts.append(f'<text x="{tx:.1f}" y="{y:.1f}" text-anchor="{anchor}" dominant-baseline="middle">{c["name"]}</text>')
    parts.append("</g></svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------------------------- main
def build(region: str, cell: float = 1000.0, scale: int = 1) -> dict:
    a = AREAS[region]
    out = ROOT / "data" / "out" / region
    out.mkdir(parents=True, exist_ok=True)
    z, tr, src = terrain(region, cell)
    poly = country_polygon(region, a["crs"])
    towns = cities(region, a["crs"])
    mask = country_mask(poly, z, tr, cell)
    rs, cs = crop_to(mask, margin=28)  # the registry frame is the lon/lat box's outer rectangle: far wider than the country
    z, mask = z[rs, cs], mask[rs, cs]
    tr = tr * rasterio.Affine.translation(cs.start, rs.start)
    polys = outline(mask, tr, cell)
    files = {}
    for theme in ("light", "dark"):
        img = draw_vectors(picture(z, mask, cell, theme, scale), polys, towns, tr, theme, scale)
        name = f"slide_{region}_{theme}.png"
        img.save(out / name, optimize=True)
        files[theme] = name
    size = (z.shape[1] * scale, z.shape[0] * scale)
    svg(out / f"slide_{region}.svg", files["light"], size, polys, towns, tr, scale)
    info = {
        "region": region, "crs": a["crs"], "frame_extent": list(a["extent"]), "cell_m": cell, "scale": scale, "size_px": list(size),
        "extent": [tr.c, tr.f + tr.e * z.shape[0], tr.c + tr.a * z.shape[1], tr.f],  # the cropped picture, metres in the frame CRS
        "files": {**files, "svg": f"slide_{region}.svg"},
        "style": "sky shade as ink (dark in the hollows, light on the lit slopes) on a subdued fill; outline; cities; transparent outside the country",
        "terrain": src, "country": {"source": "Natural Earth 10 m admin 0, mainland parts, land border buffered 3 cells; coast from the terrain's 0 m line"},
        "cities": [{**c, "px": list(px(tr, c["x"], c["y"], scale))} for c in towns],
        "attribution": sorted(set(src["attribution"]) | {NE_ATTRIBUTION}),
        "built": date.today().isoformat(),
    }
    (out / f"slide_{region}.json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
    return info


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("region", choices=sorted(COUNTRY))
    p.add_argument("--cell", type=float, default=1000.0, help="metres per terrain cell (default 1000)")
    p.add_argument("--scale", type=int, default=1, help="output pixels per cell (2 for a sharper slide)")
    a = p.parse_args()
    info = build(a.region, a.cell, a.scale)
    print(f"{a.region}: {info['size_px'][0]} x {info['size_px'][1]} px from the {info['terrain']['grid']} grid; "
          f"{', '.join(c['name'] for c in info['cities'])}; {', '.join(info['files'].values())}")


if __name__ == "__main__":
    main()
