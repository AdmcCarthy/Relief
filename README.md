# Relief

**Open topography and bathymetry, generalised into fast contour maps for data visualisation.**
Techniques page: https://admccarthy.github.io/Relief/ · vector layers: https://admccarthy.github.io/Relief/vector.html

Reusable across areas and stories (SubScout figures, MapLibre maps): land heights from the Copernicus DEM,
sea-floor depths from the EMODnet Bathymetry DTM, merged, projected, contoured into stacked layers at several
levels of detail and generalised by scale, with a hillshade for optional shading. Styles: muted context
tints for data overlays, hypsometric "showcase" tints with hillshade, or contour lines; light and dark.

Status: **proof of concept** for Vestland (Bergen coast: fjords, skerries, the Norwegian Trench).
Plan: [docs/plan.md](docs/plan.md). Data sources and licences: [docs/sources.md](docs/sources.md).

```
uv sync --all-groups
uv run python scripts/fetch.py vestland   # -> data/raw/vestland (~70 MB; not committed)
uv run python scripts/build.py vestland   # -> data/out/vestland: <lod>.geojson, <lod>_hillshade.png, manifest.json
uv run python scripts/fetch_kartverket_sea.py vestland && uv run python scripts/fetch_glaciers.py vestland
uv run python scripts/render_demo.py vestland  # -> data/out/vestland/demo: 16-bit elevation WebP, glacier mask, comparisons
uv run pytest
```

Attribution: Copernicus DEM GLO-90 © DLR e.V. 2010–2014 and © Airbus 2014–2018, provided under COPERNICUS by
the European Union and ESA. EMODnet Bathymetry Consortium (2024): EMODnet Digital Bathymetry (DTM).
Code: MIT.
