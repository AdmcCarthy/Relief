# Print layers

Relief owns terrain processing: sources, contours, hillshade, generalisation by scale. Map makers (Sheet, SubScout
maps, anything else) do not contour, shade or resample terrain themselves. They ask Relief for the layers of one frame
and draw the result.

```
uv run python scripts/print_layers.py north_sea --scale 1500000 --dpi 150 --out _layers/ns \
    [--extent x0,y0,x1,y1] [--layers elevation,zones,hillshade,contours,coast] [--source auto|tiles|hires]
```

**Contract.** Everything lands in `--out`, georeferenced in the region CRS (metres), described by `layers.json`
(`relief_layers: 1`): CRS, extent, scale, dpi, source level, per-file encoding and parameters, attribution.

| File | Content |
|---|---|
| `elevation.tif` | float32 heights, sea negative, on the coarsest tile level no coarser than one print pixel (finest if none) |
| `zones.tif` | uint8 RGB climate-zone weights (temperate, boreal, tundra; arid = remainder) |
| `hillshade.tif` | uint8 = shade multiplier x 100 (100 flat, 0..160); soft six-light model as in `preview/relief.js`; slopes over one print pixel |
| `contours.geojson` | MultiLineString per level; `z` (m, depth negative), `kind`, `index` (every 5th); 0 m excluded |
| `coast.geojson` | the 0 m line, generalised harder |

**Generalisation by scale** (the rule in plan.md, now applied per print frame): heights are averaged down to about one
print pixel (never up); contours are traced on a grid at least as fine as half a pixel, blurred 0.7 cell, simplified at
0.04 mm, smoothed (Chaikin x2), re-thinned and dropped under 4 mm; intervals step with scale (sea/land m: 25/50 to 1:250k,
50/100 to 1:750k, 100/200 to 1:2.5M, 250/500 to 1:7.5M, then 500/1000).

**Source.** `auto` and `tiles` read the committed pyramid (`data/out/<region>/tiles`), so the product is reproducible
from the repo; `hires` reads `data/raw/<region>/hires.tif`. The scripts never fetch.

Tests: `tests/test_print_layers.py` (scale rules, hillshade neutrality and light direction, contour generalisation,
level choice, a real run on the North Sea tiles).
