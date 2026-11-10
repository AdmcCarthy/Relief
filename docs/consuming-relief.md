# Consuming Relief

Relief publishes terrain once so that other repos draw it and never rebuild it. This note is the agreement: what a consumer
can pin, fetch and read, and what Relief promises not to break. The look of the terrain is in [base-maps.md](base-maps.md);
the release mechanics are in [data-releases.md](data-releases.md).

## Pin a release

Releases are immutable and tagged by date. A consumer pins one tag and moves it deliberately.

| Tag | Holds | Use |
|---|---|---|
| `data-YYYY-MM-DD` | built layers per region: tiles, vectors, hillshade, base images | drawing |
| `grids-YYYY-MM-DD` | merged elevation grids per region | rebuilding layers without the slow fetch |

```
uv run python scripts/fetch_data.py --list                         # every release, with its regions
uv run python scripts/fetch_data.py --tag data-2026-11-09-gebco north_sea --dest data/relief
```

Each fetch checks the release manifest against the contract, then the sha256 of every archive. A public repository needs no
token. The live site serves the latest data release under `https://admccarthy.github.io/Relief/data/<region>/`, which suits a
prototype; a published product should read a pinned tag.

## What a region folder holds

`data/out/<region>/` after a fetch (or under `data/<region>/` on the site):

| File | Read it for |
|---|---|
| `manifest.json` | `area`, `name`, `crs` (proj4 string), `extent` and `bbox` (`[x0, y0, x1, y1]` in the region CRS and in lon/lat), `land` and `sea` band levels, `lods` |
| `<lod>.geojson` | stacked ("layer cake") polygons per level of detail, pre-projected in region metres: draw with an identity transform |
| `<lod>_hillshade.png` | hillshade for the same rectangle as the LOD's `bounds` |
| `regional_base_{light,dark}.png` | the Detuned base map; named under `manifest.base.regional` |
| `demo/elev.webp`, `demo/zones.png`, `demo/meta.json` | one 16-bit elevation texture (height = `encoding.base` + (R × 256 + G) × `encoding.step`) and the climate-zone weights |
| `tiles/tiles.json`, `tiles/<z>/<x>_<y>.webp` | the same heights as a pyramid of 512 px tiles, level 0 coarsest |

Only the keys listed in `scripts/contract.py` are part of the agreement; other keys in a manifest are private. A region may have
fewer levels of detail than another (the world has no `detail`), so read `manifest.lods` and do not assume three.

## What is promised

The contract has a version, `CONTRACT` in `scripts/contract.py`, written into every release manifest as `contract`.

- Adding a key, a file or a region does not change it.
- Removing or renaming a listed key, or changing what one means, raises it, and ships only in a new release tag. Old tags
  stay as they were.
- `fetch_data.py` refuses a release whose contract is newer than the checkout understands, so an old checkout fails loudly
  and not quietly wrong. Releases from before the key existed count as version 1.
- `python scripts/contract.py check` validates a fetched `data/out/`: required keys, and that every file a manifest names
  exists, including every tile. The Pages build runs it before it deploys.

## Drawing rules that are easy to get wrong

- **Hillshade tone.** The hillshade PNGs are light: flat ground sits near 180 of 255 and slopes span about 165 to 190
  (plan-europe-frame.md records the same). A canvas soft-light composite is neutral at mid grey, so remap the PNG before
  compositing, or the terrain will barely show.
- **Colour.** Take the sea and land colours from the base images and the depth key from `manifest.base.depth_scale`; do not
  choose a ramp per map. The two sea ramps (shelf 0 to 1,300 m, ocean 0 to 7,000 m) are not interchangeable.
- **Attribution.** Every region carries its source list in `tiles.json` (`attribution`) and in the release manifest. A map
  that draws Relief terrain credits those sources and says it is not for navigation.
- **Heights are surface heights** (Copernicus and GEBCO include trees, buildings and ice), not bare-earth.

## Build on the contract, not around it

A consumer that needs something the files do not give (another frame, a different level of detail, a layer) asks Relief for
it as a new region or a new key, so that every consumer gets it. It does not contour, shade, resample or recolour the terrain
itself.
