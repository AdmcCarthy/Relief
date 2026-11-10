# Base maps for other repos

Written 2026-11-10. Relief owns the look of the terrain under other people's data, so that look is rendered once here
and drawn as it is everywhere else. Nobody specifies it per map.

## The rule

A base map is Relief's Detuned style, in this order from the bottom:

1. **Sea floor: a linear gradient** on the region's depth scale. Shelf regions (North Sea, NE Europe, Barents Sea,
   Vestland) run 0 to 1,300 m; ocean regions (Norwegian Sea, Atlantic, world) run 0 to 7,000 m. Both ramps are in
   `preview/palette.js` and `docs/depth-scale.md`; never stepped, never contoured.
2. **Land: stepped height classes** (0, 50, 150, 300, 600, 1,000, 1,500, 2,000 m), each class coloured by the climate
   zone ramps at half saturation and cross-blended by the Köppen-Geiger zone weights (Beck and others 2023), so lowland
   tints vary with climate and the uplands share one alpine ramp.
3. The consumer's own data.
4. **Hillshade** on top, composited so the terrain shows through the data (soft-light; the consumer remaps the PNG so flat
   ground is mid grey until the hillshade is written neutral).
5. The depth key, read from the manifest, drawn as a linear bar with the ticks the manifest names.

## The product

```
uv run python scripts/base_tint.py ne_europe north_sea norwegian_sea
# the Köppen-Geiger raster these need is fetched on first use (scripts/fetch_climate.py, 131 MB, md5-checked)
```

writes, for each region, `data/out/<region>/regional_base_light.png` and `regional_base_dark.png` (RGB, the regional
LOD grid, the region's extent, from the demo elevation texture and `zones.png`) and records in `manifest.json`:

```json
"base": {
  "regional": {"light": "regional_base_light.png", "dark": "regional_base_dark.png"},
  "style": "Detuned: linear bathymetry on the shelf depth scale, stepped land classes cross-blended by climate zone",
  "depth_scale": {"kind": "shelf", "max_m": 1300, "ticks_m": [0, 250, 500, 1000]},
  "land_classes_m": [0, 50, 150, 300, 600, 1000, 1500, 2000],
  "note": "Draw this image with an identity transform in the frame extent, your data over it, then the hillshade."
}
```

The files are part of the data release with the other layers (`scripts/publish_data.py`), so a consumer fetching a
release gets them with the hillshade and the bands.

## Drawing it (d3, canvas)

```js
const man = await (await fetch(`${reliefDir}/manifest.json`)).json();
const img = new Image(); img.src = `${reliefDir}/${man.base.regional[dark ? "dark" : "light"]}`; await img.decode();
const [x0, y0, x1, y1] = man.extent, a = proj([x0, y1]), b = proj([x1, y0]);
ctx.drawImage(img, a[0], a[1], b[0] - a[0], b[1] - a[1]);     // 1 and 2
// ... your data ...                                           // 3
// ... hillshade, soft-light ...                               // 4
// depth key: a linear bar on the ramp for man.base.depth_scale.kind, ticks at man.base.depth_scale.ticks_m
```

The stops for the key are the same lists as `preview/palette.js` (`DETUNED_SEA`, `DETUNED_OCEAN`); a consumer that
needs them copies those two lists and says so. `tests/test_base_tint.py` keeps the Python and the JS stops identical.

## Why linear sea and stepped land

Shelf bathymetry carries its information in gentle gradients (the Norwegian Trench's edge, the Dogger Bank, the Baltic
sills), which steps turn into false shorelines; land reads better in classes because hypsometric tints are a convention
readers know and because the data drawn on land needs a quiet, flat background between the steps. The house style has
said this since 2026-11-08 (plan.md, "Styles"); this note makes it the default for every consumer rather than a choice
each map has to make.
