# Relief: working rules

Open topography and bathymetry for data maps, reusable by any story (SubScout) or map. Owner: Adam McCarthy.

@../../shared/idiom/CORE.md

Voice and structure of written work (README, docs, published pages) follow Idiom's CORE.md and house style: British English, impersonal, one creative headline then plain varied headings, a section ends on its last point. The import is harmless when the file is absent (CI).

- Open sources only; record licence and attribution in docs/sources.md and on every output.
- Generalise by intended map scale (LOD config in scripts/build.py): cell size, smoothing, min feature area and
  gap closing in cells. Stacked ("layer cake") contours; pre-projected metres rounded to 10 m.
- Disk is small (10 GB): fetch only area boxes (WCS / single tiles), never whole datasets; data/raw is ignored.
- Built layers (data/out/<region>, except vestland) are NOT committed: publish them as release assets (scripts/publish_data.py, docs/data-releases.md); the Pages workflow runs scripts/fetch_data.py. Only plan sources with an open, recorded licence (redistributable); the Kartverket seamless terrain WCS is excluded (Norge digitalt licence).
- Tests (tests/) check nesting, generalisation and size/draw budgets. British English, metric.
- Regions live in regions/regions.json (single source of truth, reused by other apps): edit it, then `scripts/regions.py sync`; never hand-edit extent/bbox. Coverage claims are checked against Sodir data by `regions.py check` and tests.
- Examples use one fixed style: Detuned, stepped relief, linear bathymetry, no contours, no illumination. Source plan: regions/sources.json; long builds go through scripts/build_hires.py (plan first; never run a fetch without being asked). Fine data is delivered as tile pyramids (scripts/build_tiles.py -> data/out/<region>/tiles/), viewed on explore.html.
- Browser JS can be run: Node is at ~/.local/node/bin (add to PATH) and Playwright's Chromium is cached in ~/.cache/ms-playwright; `tests/e2e/check_pages.mjs` smoke-tests the gallery and zoom viewer (setup in its header). `node --check` on a .mjs copy syntax-checks a page script.
- Print layers: terrain processing for map sheets lives here (`scripts/print_layers.py`, docs/print-layers.md): other repos consume its files and never contour, shade or resample terrain themselves. Keep the `layers.json` contract (`relief_layers: 1`) stable.
- Sea colour: two linear ramps (shelf 0-1,300 m, ocean 0-7,000 m) chosen per region by `bathymetry` in regions.json; designed and checked by scripts/depth_ramp.py (OKLCH, lightness monotonic, even delta E per 500 m), mirrored in preview/palette.js and guarded by tests/test_depth_ramp.py. Change the generator and the JS together.
- Print layers: terrain processing for map sheets lives here (`scripts/print_layers.py`, docs/print-layers.md): other repos consume its files and never contour, shade or resample terrain themselves. Keep the `layers.json` contract (`relief_layers: 1`) stable.

## Idiom (private repo)

Idiom is Adam McCarthy's private repo (`github.com/AdmcCarthy/Idiom`; `gh repo clone AdmcCarthy/Idiom` with access, normally linked at
`../../shared/idiom`) of voice, house style, working rules and the lookup tables agents use first: `DIRECTORY.md` says which repo already
does a job, `DATASETS.md` gives every dataset's terms, attribution line and status. Read the relevant one before choosing a repo or
using data, and update it when you learn something new. Never copy anything from its `personal/` or `working/` folders into this repo
or quote it in public output; if the folder is not available, say so and carry on with this file.
