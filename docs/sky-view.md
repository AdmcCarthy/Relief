# Sky light: the sky-view factor as an ambient term

A hillshade lights each slope by its own gradient, so a fjord floor and an open plain under the same slope take the
same tone. Relief's soft model (six lights round the compass plus a sky term from the normal) keeps every slope out of
black, and the hard model (one light at 315/45) gives the strongest ridges, but neither knows where a cell stands.
The sky-view factor does: the share of the sky dome a cell can see once the horizon is taken into account (Zakšek,
Oštir and Kokalj 2011). A trench floor or the foot of a wall sees a thin strip and darkens; a plateau or a summit
sees the whole dome and lifts. Used as the ambient term of the shade it gives relief its massing without the
harshness of a low sun. Since 2026-11-15 it is the default shade wherever Relief draws one.

## The model

```
sky = soft * (1 - a * (1 - svf))        a = 0.6
```

`soft` is the six-light shade and `svf` the sky-view factor in [0, 1]. Open ground keeps the full soft shade, a cell
that sees half the sky loses a x 0.5 of its tone, and the light direction survives because the sky light scales the
soft shade rather than replacing part of it: the two faces of a ridge keep their soft contrast exactly. Flat open
ground is 1.0, as in the other models. Heights are exaggerated by the
house rule shared with the hillshades, 2 x growing with the cell beyond 1 km, so the shade and the horizon read the
same relief. The strength `a` is one constant, `AMBIENT` in `scripts/sky_view.py` and the `uSkyK` default in
`preview/relief.js`: 0.45 was the first setting, 0.6 the one chosen for a stronger sky.

The first form blended the two terms, (1 - a) soft + a sky. On the gentle regional grids that let nothing rise above
flat ground: the shipped shade for the Norwegian Sea frame had its 99th percentile at the flat value and every slope
darkened, so the light direction was gone. Multiplying, the combination the Relief Visualization Toolbox recommends
for a hillshade and a sky-view factor, keeps it.

## Where it applies

| Product | Shade | Note |
|---|---|---|
| `<lod>_hillshade.png` from `scripts/build.py` | sky | flat open ground stays at 180 of 255, so consumers' remaps and `regional_shade.webp` (base_tint.py) follow unchanged; releases made before 2026-11-15 carry the one-light model until rebuilt |
| `hillshade.tif` from `scripts/print_layers.py` | sky (default) | `--shade-model soft` or `hard` remain |
| techniques page, case cards and playground | sky | the soft and one-light cases stay as cases; the shade segment has a Sky button |
| gallery, ocean regions' sea floor | sky | land stays unshaded by the examples rule; drawn from `demo/skyview.webp`, or `skyview_card.webp` where the card texture is used |
| zoom viewer (tiles), the sea-floor resolution comparison | soft | no baked factor per tile; falls back without a message |

The WebGL renderer takes the baked factor from `scripts/sky_view.py <region>`, which writes
`data/out/<region>/demo/skyview.webp` (uint8, 255 = the whole sky, lossy WebP at quality 85: a tenth of the lossless
size on a factor this smooth), a card-sized copy where the region has one, and records both under `skyview` in
`meta.json`. A page only requests the texture when the manifest lists it, so older data releases draw with soft light
and request nothing. `scripts/build.py <region> --hillshade-only` rewrites the shipped PNGs from the merged grid without
rebuilding the vector layers; run `base_tint.py` after it for the neutral WebP.

## Why it is fast

`scripts/sky_view.py` computes the horizon in 16 lattice directions, the 8 principal ones and the 8 knight moves,
so every sample is a whole-cell shift and nothing is interpolated. Each direction is weighted by the width of its
sector (26.6° cardinal, 22.5° knight, 18.4° diagonal). Along each direction the distances grow geometrically (1, 2, 3,
4, 6, 8, 11, 16, 23, 32, 45, 64 cells, to a search radius of about 20 km held between 16 and 128 cells): a near wall
sets the horizon exactly, a far ridge is sampled at the angular resolution a far ridge needs. The horizon is the
running maximum of height difference over distance, one `np.maximum` on array slices per sample, so the whole
factor is about 190 shift-and-max passes with no Python loop over cells.

| Grid | Cells | Time |
|---|---|---|
| Vestland demo texture, 200 m | 1.37 million | 0.7 s |
| Random 1,000 x 1,000 test grid | 1 million | under 1 s (the test allows 15 s for CI) |

Beyond the frame the terrain is unknown and is treated as open sky, so a cell at the edge is at most a little
brighter than it would be with the neighbouring frame in hand.

## Where the idea comes from

The question that started this was whether radiance cascades (Sannikov 2023; Osborne and Sannikov 2024; Freeman,
Sannikov and Margel 2025) could replace hillshading. They solve global illumination in a plane: probes store short
radiance intervals at geometrically growing distances and are merged coarse to fine, at a cost that does not depend
on the number of lights. A map has one sun, one sky and one occluding surface lit from above the plane, so the
method does not transfer; adapted to a heightfield, each interval would hold a horizon angle and the merge a running
maximum, which is a horizon map. What does transfer is the sampling: geometric intervals along the ray, which is
how the sky-view factor is made cheap here.

The established terrain methods behind this are horizon mapping (Max 1988), the sky-view factor of the Relief
Visualization Toolbox (Zakšek, Oštir and Kokalj 2011; Kokalj and Somrak 2019, 16 directions to a fixed radius), and
the line-sweep algorithms that make horizon visibility exact in one pass per direction (Timonen 2013; Reusser's
line-sweep terrain lighting in the browser). The other modern road, neural relief shading trained on Swiss manual
relief (Jenny et al. 2021, the Eduard application), is not taken: it is a commercial model that cannot be
reproduced from a formula in this repo or tested for neutrality and light direction.

## What was tried and dropped

Cast shadows from a sun disc were rendered on Vestland beside this model. At the house exaggeration and a 45° sun
they cover 3 % of the cells and read as ink lines along the deepest fjord walls rather than as light; lowering the
sun makes more of them and makes them more intrusive. The sky-view term carried almost all of the visual gain, so
the shadows were dropped and the `sky` model has none.

## Use

```
uv run python scripts/print_layers.py north_sea --scale 250000 --dpi 150 --out _layers/ns      # sky by default
uv run python scripts/sky_view.py vestland                 # bake the page texture for a region
uv run python scripts/build.py north_sea_wide --hillshade-only && uv run python scripts/base_tint.py north_sea_wide
```

`layers.json` records `mode: sky`, the ambient share and the sky-view parameters under `files.hillshade`; a region
manifest records the model string under each level's `hillshade`. Tests: `tests/test_sky_view.py` (sector weights,
open ground neutral, a dome's summit sees the whole sky, a bowl's floor sees less than its rim, the light direction
survives, the shipped PNG keeps flat ground at 180, a million cells in seconds, the print-layers manifest).
