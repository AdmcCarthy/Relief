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
1. **Areas**: North Sea (SODIR licences, Wildcat), Norwegian Sea, Barents Sea (EMODnet + GEBCO north of its
   coverage), Norway land. One config line per area in `scripts/areas.py`.
2. **Coastline and lakes from Kartverket N-series**; Natural Earth for the overview.
3. **Formats**: TopoJSON (shared arcs, quantised) for d3 figures in SubScout; PMTiles vector tiles plus a
   hillshade raster PMTiles for MapLibre maps (SubScout's planned map stack), both static on GitHub Pages.
4. **SubScout integration**: a `relief` base layer for map figures (style, LOD chosen from figure scale).
5. **Quality checks**: no slivers between stacked layers, monotonic nesting (higher land inside lower land),
   size and draw-time budgets per LOD, coastline agreement with Kartverket.
6. **Vertical datum note** on maps that show shallow water.
