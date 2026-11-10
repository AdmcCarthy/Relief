# Relief

**Open topography and bathymetry, generalised into fast contour maps for data visualisation.**
Region examples: https://admccarthy.github.io/Relief/ · zoomable tiles: https://admccarthy.github.io/Relief/explore.html · techniques: https://admccarthy.github.io/Relief/techniques.html · vector layers: https://admccarthy.github.io/Relief/vector.html

Reusable across areas and stories (SubScout figures, MapLibre maps): land heights from the Copernicus DEM,
sea-floor depths from the EMODnet Bathymetry DTM, merged, projected, contoured into stacked layers at several
levels of detail and generalised by scale, with a hillshade for optional shading. Styles: muted context
tints for data overlays, hypsometric "showcase" tints with hillshade, or contour lines; light and dark.

Status: Vestland proof of concept plus six shared **regions** (North Sea, Norwegian Sea, Barents Sea in a north-polar
view with Norway at the bottom, NE Europe, the Atlantic, world). Sea colour scales: [docs/depth-scale.md](docs/depth-scale.md). Regions are defined once in `regions/regions.json` for any app to
reuse: [docs/regions.md](docs/regions.md). Plan: [docs/plan.md](docs/plan.md). Data sources and licences:
[docs/sources.md](docs/sources.md).

```
uv sync --all-groups
uv run python scripts/fetch.py vestland   # -> data/raw/vestland (~70 MB; not committed)
uv run python scripts/build.py vestland   # -> data/out/vestland: <lod>.geojson, <lod>_hillshade.png, manifest.json
uv run python scripts/fetch_kartverket_sea.py vestland && uv run python scripts/fetch_glaciers.py vestland
uv run python scripts/render_demo.py vestland  # -> data/out/vestland/demo: 16-bit elevation WebP, glacier mask, comparisons
uv run pytest
```

Built data (tiles, textures) is not in git: it is a release asset, see [docs/data-releases.md](docs/data-releases.md):

```
uv run python scripts/fetch_data.py                         # latest data release -> data/out/
uv run python scripts/publish_data.py build && uv run python scripts/publish_data.py release   # after a rebuild
```

Higher-resolution data (researched and scripted: see [docs/hires-sources.md](docs/hires-sources.md)):

```
uv run python scripts/build_hires.py plan                   # per region: sources, what runs and why, no network
uv run python scripts/build_hires.py run north_sea          # fetch -> merge -> render; hours, resumable
uv run python scripts/render_region.py north_sea            # single-texture page assets from the data on disk
uv run python scripts/build_tiles.py north_sea              # tile pyramid for the zoom page (data/out/<region>/tiles/)
```

The example pages draw every region in one fixed style: Detuned, stepped relief by climate zone, linear bathymetry,
no contours, no illumination.

Regions (large areas, fetched coarser, no whole datasets):

```
uv run python scripts/regions.py sync                       # derive extents, outlines, proj4 from regions/regions.json
uv run python scripts/fetch_region.py north_sea             # -> data/raw/north_sea/merged.tif (land + sea, lon/lat)
uv run python scripts/build.py north_sea                    # -> data/out/north_sea: layers per level of detail
uv run python scripts/fetch_sodir.py && uv run python scripts/regions.py check   # coverage against Sodir blocks and fields
```

Attribution: Copernicus DEM GLO-90 © DLR e.V. 2010–2014 and © Airbus 2014–2018, provided under COPERNICUS by
the European Union and ESA. EMODnet Bathymetry Consortium (2024): EMODnet Digital Bathymetry (DTM). World and the
sea east of 43 E: NOAA NCEI ETOPO 2022 (public domain). Sodir block and field outlines (coverage checks only): NLOD.
Code: MIT License with Acknowledgement.

## Base maps for other repos

`scripts/base_tint.py <region>` renders the Detuned base once per frame (`regional_base_{light,dark}.png`: linear
bathymetry on the region's depth scale, stepped land classes cross-blended by climate zone) and records it in the
frame's `manifest.json`. Repos that draw data on Relief draw that image, their data, then the hillshade, and print the
depth key the manifest gives; see [docs/base-maps.md](docs/base-maps.md).

## Licence and acknowledgement

MIT License with Acknowledgement ([LICENSE](LICENSE)): the MIT terms plus one condition. Anything built with this work says so,
visibly and in plain words, and does not imply endorsement: "Built with Relief by Adam McCarthy (https://github.com/AdmcCarthy/Relief)". The wording is custom, so
the licence is not OSI-approved. Third-party data and vendored code keep their own terms.
