"""Design and check the sea-floor colour ramps (OKLCH in, hex out) so the scale can be reviewed by numbers, not by eye.

Two ramps share one hue family (blue to indigo) and the same pale shallow end:
  shelf  0 to 1,300 m  for shelf and coast maps (North Sea, Barents Sea, NE Europe): the existing Detuned sea ramp
  ocean  0 to 7,000 m  for basins and the world: lightness is spread over 2,000 to 6,000 m, where spreading ridges, their
         flanks, fracture zones and the abyssal plains lie. The shelf ramp holds 76 % of the world's ocean floor in its
         last colour, so none of that structure shows.
A depth ramp is sequential: one hue family, light to dark with depth, judged by monotonic lightness and by the perceptual
step (OKLab delta E x 100) per 500 m of depth, not by categorical separation (dataviz skill).

  python scripts/depth_ramp.py            # prints the JS constants and the step table
"""

from __future__ import annotations

import math

import numpy as np

# depth (m), OKLCH lightness, chroma, hue (degrees)
OCEAN_LIGHT = [(0, .955, .020, 215), (200, .890, .040, 220), (1000, .770, .075, 232), (2000, .665, .100, 245), (3000, .570, .115, 255),
               (4000, .475, .120, 262), (5000, .385, .115, 268), (6000, .305, .105, 272), (7000, .230, .090, 275)]
OCEAN_DARK = [(0, .74, .075, 215), (200, .68, .085, 220), (1000, .575, .100, 232), (2000, .495, .110, 245), (3000, .415, .118, 255),
              (4000, .34, .120, 262), (5000, .27, .112, 268), (6000, .20, .100, 272), (7000, .13, .085, 275)]
SHELF_LIGHT = ["#e8f0f2", "#cfe1e6", "#aacdd8", "#7eb0c5", "#5891ae", "#3a6d94", "#264b73", "#162b50"]  # as palette.js DETUNED_SEA
SHELF_DARK = ["#3a8aa2", "#2f7690", "#25647d", "#1c526b", "#144157", "#0e3045", "#092336", "#06172a"]
SHELF_BREAKS, SHELF_MAX = [0, 20, 50, 100, 200, 500, 1000], 1300


def oklch_to_srgb(L: float, C: float, h: float) -> tuple[float, float, float]:
    """OKLCH to sRGB (0..1), reducing chroma until the colour is inside the sRGB gamut."""
    for c in np.linspace(C, 0, 60):
        a, b = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
        l_, m_, s_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
        rgb = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_, -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
               -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)
        if all(-1e-4 <= v <= 1 + 1e-4 for v in rgb):
            return tuple(min(1.0, max(0.0, 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)) for v in rgb)
    raise ValueError("no in-gamut colour")


def srgb_to_oklab(rgb) -> tuple[float, float, float]:
    lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    l_ = (0.4122214708 * lin[0] + 0.5363325363 * lin[1] + 0.0514459929 * lin[2]) ** (1 / 3)
    m_ = (0.2119034982 * lin[0] + 0.6806995451 * lin[1] + 0.1073969566 * lin[2]) ** (1 / 3)
    s_ = (0.0883024619 * lin[0] + 0.2817188376 * lin[1] + 0.6299787005 * lin[2]) ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_, 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def hex_of(rgb) -> str:
    return "#" + "".join(f"{round(v * 255):02x}" for v in rgb)


def rgb_of(h: str) -> tuple[float, float, float]:
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


def ocean_hex(table) -> list[str]:
    return [hex_of(oklch_to_srgb(L, C, h)) for _, L, C, h in table]


def ocean_breaks(table) -> list[int]:
    return [d for d, *_ in table]


def sample(stops: list[tuple[float, tuple]], depth: float, top: float):
    """The shader's lookup: depth/top picks a point on the piecewise-linear ramp (sRGB interpolation), clamped at the ends."""
    t = min(1.0, max(0.0, depth / top))
    xs = [p for p, _ in stops]
    return tuple(float(np.interp(t, xs, [c[i] for _, c in stops])) for i in range(3))


def ramp_stops(breaks, hexes, top):
    return [(b / top, rgb_of(h)) for b, h in zip(breaks, hexes, strict=True)]


def step_table(stops, top, depths=range(0, 7001, 500), step=500):
    """OKLab delta E (x100) between a depth and `step` m deeper, for each depth."""
    out = []
    for d in depths:
        a, b = srgb_to_oklab(sample(stops, d, top)), srgb_to_oklab(sample(stops, d + step, top))
        out.append((d, 100 * math.dist(a, b), srgb_to_oklab(sample(stops, d, top))[0]))
    return out


def ramps() -> dict:
    return {
        "shelf_light": ramp_stops(SHELF_BREAKS + [1300], SHELF_LIGHT, SHELF_MAX) if False else
        [(b / SHELF_MAX, rgb_of(h)) for b, h in zip(SHELF_BREAKS + [SHELF_MAX], SHELF_LIGHT, strict=False)],
        "ocean_light": ramp_stops(ocean_breaks(OCEAN_LIGHT), ocean_hex(OCEAN_LIGHT), 7000),
        "ocean_dark": ramp_stops(ocean_breaks(OCEAN_DARK), ocean_hex(OCEAN_DARK), 7000),
    }


if __name__ == "__main__":
    print("OCEAN_SB =", ocean_breaks(OCEAN_LIGHT))
    print("light:", ocean_hex(OCEAN_LIGHT))
    print("dark: ", ocean_hex(OCEAN_DARK))
    r = ramps()
    old = step_table(r["shelf_light"], SHELF_MAX)
    new = step_table(r["ocean_light"], 7000)
    print("\ndepth   old dE   new dE   old L   new L")
    for (d, eo, lo), (_, en, ln) in zip(old, new, strict=True):
        print(f"{d:>5}   {eo:6.1f}   {en:6.1f}   {lo:.3f}   {ln:.3f}")
