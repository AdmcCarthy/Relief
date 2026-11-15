# Relief: working rules

Open topography and bathymetry for data maps, reusable by any story (SubScout) or map. Owner: Adam McCarthy.

@../../shared/idiom/CORE.md

Voice and structure of written work (README, docs, published pages) follow Idiom's CORE.md and house style: British English, impersonal, one creative headline then plain varied headings, a section ends on its last point. The import is harmless when the file is absent (CI).

- Open sources only; record licence and attribution in docs/sources.md and on every output.
- Generalise by intended map scale (LOD config in scripts/build.py): cell size, smoothing, min feature area and
  gap closing in cells. Stacked ("layer cake") contours; pre-projected metres rounded to 10 m.
- Disk is small (10 GB): fetch only area boxes (WCS / single tiles), never whole datasets; data/raw is ignored.
- Built layers (data/out/<region>, except vestland) are NOT committed: publish them as release assets (scripts/publish_data.py, docs/data-releases.md); the Pages workflow runs scripts/fetch_data.py. Only plan sources with an open, recorded licence (redistributable); the Kartverket seamless terrain WCS is excluded (Norge digitalt licence).
- Rebuild a region's layers from its merged grid with `scripts/rebuild.py plan|run` (stale stages only; never fetches sources). Restore grids on a new machine with `scripts/fetch_data.py --grids` (docs/data-releases.md).
- Tests (tests/) check nesting, generalisation and size/draw budgets. British English, metric.
- Regions live in regions/regions.json (single source of truth, reused by other apps): edit it, then `scripts/regions.py sync`; never hand-edit extent/bbox. Coverage claims are checked against Sodir data by `regions.py check` and tests.
- Examples use one fixed style: Detuned, linear relief (stepped classes until 2026-11-15, user decision), linear bathymetry, no contours, and since 2026-11-15 (user decision) the sky shade on land and sea floor alike (palette.js detunedStyle: land 0.35, sea 0.9, ocean basins 0.8 with their own exaggeration from oceanShade; the baked `demo/skyview.webp`, soft light where a release has none; docs/depth-scale.md). The gallery, the zoom viewer and the techniques page all draw it; the consumers' base tints stay flat because the shade is the layer they draw over them. Source plan: regions/sources.json; long builds go through scripts/build_hires.py (plan first; never run a fetch without being asked). Fine data is delivered as tile pyramids (scripts/build_tiles.py -> data/out/<region>/tiles/), viewed on explore.html.
- Browser JS can be run: Node is at ~/.local/node/bin (add to PATH) and Playwright's Chromium is cached in ~/.cache/ms-playwright; `tests/e2e/check_pages.mjs` smoke-tests the gallery and zoom viewer (setup in its header). `node --check` on a .mjs copy syntax-checks a page script.
- Consumers read releases through the contract in `scripts/contract.py` (docs/consuming-relief.md): changing a listed key raises `CONTRACT` and needs a new release tag; `python scripts/contract.py check` validates `data/out/`.
- Print layers: terrain processing for map sheets lives here (`scripts/print_layers.py`, docs/print-layers.md): other repos consume its files and never contour, shade or resample terrain themselves. Keep the `layers.json` contract (`relief_layers: 1`) stable. Shade models are `sky` (the default since 2026-11-15 wherever Relief draws a shade: the soft shade multiplied by the sky light, 1 − 0.6 × (1 − sky-view factor), `scripts/sky_view.py`, docs/sky-view.md), `soft` and `hard`; there are no cast shadows by decision. The shipped `<lod>_hillshade.png` keeps flat ground at 180 of 255 under the new model; `build.py <region> --hillshade-only` rewrites it from the merged grid, `sky_view.py <region>` bakes the page texture.
- **Base maps for consumers are Relief's, rendered once.** `scripts/base_tint.py <region>` writes `data/out/<region>/regional_base_{light,dark}.png` (recorded under `base` in `manifest.json`): the sea floor as a LINEAR gradient on the region's depth scale, the land as a LINEAR gradient too (0 to 2,000 m; stepped classes until 2026-11-15) cross-blended by climate zone, the Detuned style. Every repo that draws data on Relief (Bedrock, source-to-sink, ds-sand-from-the-source, Sheet, SubScout figures) draws that image with an identity transform in the frame extent, its data over it, then the hillshade, and prints the depth and height keys the manifest gives (`base.depth_scale`, `base.land_scale`). No consumer colours Relief's bands or heights itself, and nobody has to ask for "linear sea, linear land" again: it is the default. docs/base-maps.md.
- Slide map (2026-11-15): `scripts/slide_map.py norway` cuts one country out of the terrain for slides (sky shade as ink on a nearly transparent fill, outline, cities, transparent outside; docs/slide-map.md). Its frame `norway` is registered in regions.json but not built: the picture is warped from the europe_s2s grid until `build_hires.py norway` is asked for. Outline and cities are Natural Earth 10 m (`scripts/fetch_natural_earth.py`, public domain, attribution line in the JSON).
- Sea colour: two linear ramps (shelf 0-1,300 m, ocean 0-7,000 m) chosen per region by `bathymetry` in regions.json; designed and checked by scripts/depth_ramp.py (OKLCH, lightness monotonic, even delta E per 500 m), mirrored in preview/palette.js and guarded by tests/test_depth_ramp.py. Change the generator and the JS together.

## Idiom (private repo)

Idiom is Adam McCarthy's private repo (`github.com/AdmcCarthy/Idiom`; `gh repo clone AdmcCarthy/Idiom` with access, normally linked at
`../../shared/idiom`) of voice, house style, working rules and the lookup tables agents use first: `DIRECTORY.md` says which repo already
does a job, `DATASETS.md` gives every dataset's terms, attribution line and status. Read the relevant one before choosing a repo or
using data, and update it when you learn something new. Never copy anything from its `personal/` or `working/` folders into this repo
or quote it in public output; if the folder is not available, say so and carry on with this file.
