# Plan

Goal: reusable, open, fast topography and bathymetry for data visualisation: contour layers with colour fills
or shading that give geographic context without competing with the data drawn on top.

## Principles
1. **Open data only**, with licences and attribution recorded (docs/sources.md) and carried on every map.
2. **Generalise by map scale, not by file size.** Each level of detail (LOD) has a cell size, smoothing, a
   minimum feature area and a gap-closing distance in screen pixels at its intended scale.
3. **Stacked contours** (each level is "everything above/below this"), drawn bottom-up: colour fills have no
   slivers after simplification, and any band can be dropped.
4. **Pre-projected coordinates** in metres, rounded to 10 m: the browser draws with an identity transform.
5. **Styles are separate from data**: context (muted, for data overlays), showcase (hypsometric tints plus
   hillshade), contours (lines). Light and dark from the same layers.

## The Norwegian islands problem
Norway's coast has well over 200,000 islands and skerries. Rules, applied per LOD:
- drop islands and lakes under `min_area_px` cells (a few screen pixels);
- merge skerry fields with a closing (buffer out, buffer in) of `close_px` cells, so an archipelago reads as a
  textured coast instead of noise, and narrow sounds close at small scales;
- simplify with topology preserved at half a cell;
- next: use Kartverket N50/N250 coastlines for the 0 m line at regional and detail scales, keep islands by
  area *and* by importance (inhabited, named, near data features), and measure how many survive per LOD.

Proof of concept (Vestland, 3.5–7.5°E, 59–61.5°N): coastline pieces 1,049 → 262 at 125 m, 134 → 87 at
250 m, 11 → 6 at 1 km; files 0.11 / 0.90 / 2.2 MB (uncompressed GeoJSON); draw 3 / 18 / 48 ms on canvas.

## Roadmap
1. **Areas** (done 2026-11-08): North Sea, Norwegian Sea, Barents Sea (north-polar, Norway at the bottom), NE Europe, world,
   all in `regions/regions.json` with coverage checked against Sodir blocks and fields (see docs/regions.md). Next: Norway
   land areas, UK/Dutch/Danish detail, GEBCO instead of ETOPO east of 43 E.
2. **Coastline and lakes from Kartverket N-series**; Natural Earth for the overview.
3. **Formats**: TopoJSON (shared arcs, quantised) for d3 figures in SubScout; PMTiles vector tiles plus a
   hillshade raster PMTiles for MapLibre maps (SubScout's planned map stack), both static on GitHub Pages.
4. **SubScout integration**: a `relief` base layer for map figures (style, LOD chosen from figure scale).
5. **Quality checks**: no slivers between stacked layers, monotonic nesting (higher land inside lower land),
   size and draw-time budgets per LOD, coastline agreement with Kartverket.
6. **Vertical datum note** on maps that show shallow water.

## Research notes (2026-11-08)

**Climate-aware hypsometric tints.** Patterson & Jenny's *cross-blended hypsometric tints* (Cartographic
Perspectives 69, 2011; user study in 75, 2014) keep elevation steps but vary lowland colours by environment:
green in humid regions, no green in arid ones, so tints stop implying vegetation that is not there. The
Natural Earth raster uses it. Feasible with public data: **Beck et al. (2023) Köppen–Geiger 1 km, 1991–2020,
CC BY 4.0** (one 12 MB GeoTIFF). Relief groups classes into temperate, boreal, tundra/polar and arid, blurs
zone weights over ~6 km (cross-blending) and mixes four land ramps below 1,000 m in the shader; above
1,000 m all zones share one alpine ramp. Vestland: 67 % boreal, 23 % temperate, 10 % tundra, no arid.

**Non-linear steps.** Sea: 0–20, 20–50, 50–100, 100–200, 200–500, 500–1,000, >1,000 m. Land (coarser):
0–50, 50–150, 150–300, 300–600, 600–1,000, 1,000–1,500, 1,500–2,000, >2,000 m. Colour bars draw each step at
equal width so the fine shallow steps stay readable.

**Sea-floor shading.** Soft multi-directional shading works on the 50 m (Kartverket) and 115 m (EMODnet)
surfaces with ~3x vertical exaggeration; on 450 m GEBCO it mostly shows the grid, so keep it off or weak.

**Combined sea floor** (`scripts/seabed.py`): Kartverket 50 m > Denmark 50 m (needs a free Dataforsyningen
token: drop GeoTIFFs in `denmark_dybdemodel50/`) > EMODnet 115 m > GEBCO 450 m, feathered over 1.5 km.
Kartverket vs EMODnet over 0.5 M overlapping cells: median 0 m, 90 % within 4.2 m.

**Line simplification and smoothing** (`scripts/smooth.py`, `contours_visual.py`): Douglas–Peucker selects
critical points (good for minimal simplification, poor at caricature); Visvalingam–Whyatt removes the least
significant points first (more natural at small scales); Chaikin corner cutting converges to a quadratic
B-spline inside the original; centripetal Catmull–Rom (alpha 0.5) passes through the points without cusps or
self-intersections within segments (Yuksel et al. 2011). Topology-preserving DP is essential: without it,
Chaikin amplified 3 kinks into 76 self-crossing rings. Recommended visual layer: Gaussian pre-blur (1 cell) +
DP (1.5 cells) + Chaikin x2: 71 % fewer points than raw, no self-crossings, calm curves. The precise grid
stays the record; the visual layer is for drawing (aesthetics over contour precision, as agreed).

## Region examples and higher-resolution data (2026-11-08)
The landing page now leads with the regions in one fixed style (Detuned, stepped relief, linear bathymetry, no contours,
no illumination); the twelve-case techniques page moved to `techniques.html`. Better sources were researched per region
(docs/hires-sources.md) and are scripted in `scripts/build_hires.py` (plan, fetch, merge, render; resumable; manual drop-in
for GEBCO, IBCAO, Danish and German models). Not run yet. Next: run it for Barents Sea and the world first (largest real
gain), then tiled elevation delivery so 25 to 50 m data is visible when zoomed.

## Styles (2026-11-08)
All land tints are now cross-blended by climate zone (one ramp per Köppen–Geiger group below 1,000 m, a shared
alpine ramp above); the styles differ in how far they are detuned from that full-strength **relief** set:
- **Relief**: full-strength tints, moderate shading (land 0.6, sea 0.45).
- **Context**: the same ramps at 0.38 saturation, lifted (light) or sunk (dark), light shading: a quiet base for data.
- **Sea floor**: land at 0.18 saturation, sea at full strength, strong sea shading (0.75).
- **Detuned** (house style): land at half saturation; sea floor on its own wider, deeper indigo ramp with
  strong shading (0.9), stepped or linear.
The coastline is off by default (at skerry scale it reads as noise); when switched on it is drawn at 30 %
opacity. Contour lines skip the 0 m level for the same reason. Colour bars show one height strip per climate
zone present, then depth.
