# Plan: a Europe frame with hillshade for the source-to-sink work

**Status 2026-11-10, evening.** Steps 1 to 6 done on the owner's go-ahead: `europe_s2s` registered (`fit: outer` on the
lon/lat box gives 3,720 × 3,060 km, larger than the estimate below, because the box's corners spread in LAEA); fetched
with `build_hires.py` (Copernicus GLO-90, EMODnet 2024, ETOPO 2022; 65 MB raw), merged at 1,600 m, demo assets rendered,
layers built at 8,000 / 4,000 / 1,600 m (16 MB), 29 tiles, base tints on the ocean scale. The hillshade keeps its tone
and the manifest now states its flat value (180) instead. Step 7 (release `publish_data.py release`) waits for the owner
because creating a release is a new public surface; step 8 is open: source-to-sink's `europe` region (the parallel
session's) still points at `relief: atlantic`; `relief: europe_s2s` is the drop-in replacement.

Written 2026-11-10 at the owner's request. This is a plan, not a build: nothing here has been fetched or run. It sets out
what Relief would need to add so that one frame carries terrain and hillshade for every catchment that `source-to-sink`
analyses and `Sand-from-the-Source` and `Bedrock` display, and what it would cost in disk, time and licence.

## Why the present frames fall short

The analysis runs on three Relief frames: `ne_europe` (EPSG:3035, 12 W to 30 E, 46.8 N to 62.2 N), `north_sea`
(UTM 32N) and `norwegian_sea` (Lambert conformal, to 70.4 N). Between them they leave out ground the catchments cover:

- Fennoscandia north of 62 N east of the Norwegian Sea frame: the Swedish and Finnish rivers to the Gulf of Bothnia
  (Lule, Torne, Kemi, Oulu), northern Norway and Finnmark.
- The east: Lake Ladoga and the Neva (to 35 E), the Daugava and Neman headwaters.
- The south: the Rhine, Elbe, Oder and Vistula headwaters in the Alps, the Bohemian massif and the Carpathians (to 46 N
  and a little below); the Loire and Seine basins to the Massif Central.
- Ireland's west coast at 10.5 W is inside the frame; Rockall is not needed.

Catchments are drawn whole (`source-to-sink` keeps HydroSHEDS systems entire), so a Vistula or a Neva is cut off by the
frame edge today and its upland relief, which drives the BQART budget, is read from Relief's tiles only where tiles exist.
One frame that holds every catchment from Ireland to Ladoga and from the Alps to the North Cape removes that cut and makes
one hillshade, one depth scale and one height scale serve the story, the gallery and the budget.

Two other things the consumers have had to work around, and which this frame should settle at the source:

1. **Hillshade tone.** The `*_hillshade.png` layers are light (flat ground sits near 180 of 255, slopes span about 165 to
   190), so a consumer compositing them with canvas soft-light, which is neutral at mid grey, sees almost nothing and has to
   remap them. The frame's hillshade should either be written with flat ground at mid grey (128) or carry its flat value and
   range in `manifest.json` so a consumer can remap without guessing.
2. **Climate zones for the frame.** The budget reads one mean temperature per climate zone from `demo/zones.png`; the new
   frame needs the same `zones.png` (Beck and others 2023 weights) over its whole extent.

## The frame

| | Proposal |
|---|---|
| `id` | `europe_s2s` (a working name; `europe` is kept free for a continent-wide locator frame) |
| CRS | ETRS89 / LAEA Europe, EPSG:3035, the same as `ne_europe`, so the two frames nest and consumers' identity transforms carry over |
| `design.lonlat_box` | `[-11.5, 44.5, 36.0, 71.5]`, `fit: outer`; `north_at: [71.5, 25]` so the North Cape sits inside |
| Extent (estimate, before `regions.py sync`) | about x 2,600,000 to 5,900,000, y 2,500,000 to 5,450,000: 3,300 × 2,950 km |
| `bathymetry` | `shelf` for the North Sea, Baltic and Irish Sea; the Norwegian Sea basin and the Atlantic west of Ireland pass 1,300 m, so the frame should carry **both** levels sets and the consumer chooses (the viewers already switch ramps by `bathymetry`); or `ocean` with the shelf's fine steps added to `levels.sea` |
| `levels.sea` | `[0, 20, 50, 100, 150, 200, 300, 500, 1000, 1500, 2000, 3000]` |
| `levels.land` | `[0, 100, 250, 500, 750, 1000, 1500, 2000, 3000]` (the Alps reach 4,800 m; 3,000+ is one class) |
| `lods` | overview 8,000 m (413 × 369 cells), regional 4,000 m (825 × 738), detail 1,600 m (2,063 × 1,844); the cell rule of plan.md at 1:15M, 1:7.5M and 1:3M |
| `fetch.step_deg` | 0.00833 (30 arc-second, as `ne_europe`) for land and shelf; GEBCO or ETOPO for the deep basin |

The frame is 2.7 times the area of `ne_europe`. At 30 arc-seconds the raw grid is about 5,700 × 3,240 cells (74 MB as
float32), within the disk rule if the raw fetch is boxed and deleted after the build.

## Sources and licence

All already in `docs/sources.md` and Idiom `DATASETS.md`; nothing new has to be cleared:

- Land: Copernicus DEM GLO-90 (ESA, free with attribution), as the other frames; GLO-30 is not needed at these cells.
- Shelf: EMODnet Bathymetry 2024 DTM (free with attribution), which covers the whole European shelf including the Baltic
  and the Gulf of Bothnia.
- Deep sea west of the shelf edge: GEBCO 2026 (free, citation) where the EMODnet grid ends, else ETOPO 2022.
- Climate zones: Beck and others (2023), Köppen-Geiger 1991 to 2020, 1 km, CC BY 4.0.
- Kartverket terrain is excluded (Norge digitalt licence), as the working rules say.

## Work, in order

1. **Region.** Add the entry to `regions/regions.json`; `uv run python scripts/regions.py sync`. Add a `coverage` block
   that checks every HydroSHEDS system `source-to-sink` names (Vistula, Neva, Rhine, Elbe, Oder, Glomma, Lule, Kemi,
   Shannon, Severn, Loire) lies inside by at least 99 per cent of its area, with `regions.py check` reading the catchment
   outlines from `source-to-sink/data/derived/<region>/systems.parquet` or a committed list of bounding boxes. About half a
   day including the test.
2. **Fetch plan.** `scripts/build_hires.py plan europe_s2s` to list the EMODnet and Copernicus tiles the box needs and
   their sizes; confirm the total stays under 3 GB raw. No fetch is run until the owner says so. One hour.
3. **Fetch and build.** `fetch_region.py europe_s2s` then `build.py europe_s2s`, one LOD at a time (the Greenland and
   Norway builds in the sibling repos were killed for memory when run together; this frame is larger than any built so far).
   Estimated 20 to 40 minutes of machine time per LOD on this laptop; contours and band nesting checked by the existing
   tests. Half a day with checks.
4. **Hillshade products.** Write `regional_hillshade.png` and `overview_hillshade.png` as now, plus:
   - the soft multi-directional model as default and the `hard` single-light model as an option (`print_layers.py` already
     has both; expose the choice in `build.py` so the frame can ship both files, `*_hillshade.png` and `*_hillshade_hard.png`);
   - **neutral tone**: write the PNG so that flat ground is 128 and the shade multiplier maps 0..160 to 0..255 around it,
     and record `hillshade: {flat: 128, range: [0, 255], model: "soft"}` in `manifest.json`. Keep the old light tone for the
     existing frames until their consumers are moved, or write both and let the manifest say which is which.
   Half a day, with a test in `tests/test_print_layers.py` that the PNG's median over flat sea is within 2 of the stated flat.
5. **Climate zones.** Render `demo/zones.png` for the frame at the regional cell (the same weights the budget reads) and
   list it in the manifest. One hour.
6. **Tiles.** `scripts/build_tiles.py europe_s2s` for the explore page and for `source-to-sink`'s relief reader, which
   takes the maximum elevation per catchment from tile level 1. The tile pyramid for `ne_europe` is 31 MB; this frame would
   be about 80 MB. Decide whether to publish the full pyramid or only levels 0 to 2 as a release asset. Two hours.
7. **Release and Pages.** `scripts/publish_data.py` to a `data-europe_s2s` release; `fetch_data.py` in the Pages
   workflow; `docs/regions.md` and `docs/data-releases.md` updated; Idiom `DATASETS.md` row for the frame. One hour.
8. **Consumers.** `source-to-sink` adds the region in `config/regions.yaml` (`relief: europe_s2s`) and rebuilds; the
   `Sand-from-the-Source` extractor gains the frame; `Bedrock` publishes it. Outside Relief; a day across the three repos,
   mostly waiting on builds.

Total inside Relief: about two and a half days of work, most of it machine time, in eight steps that each leave the repo
in a working state. Steps 1, 2, 4 and 5 can be done without any fetch; 3, 6 and 7 need the owner's go-ahead because they
download data and publish a release.

## Risks and what to decide first

- **Memory.** The machine has killed background builds at 2,000 m cells on smaller frames. Build one LOD per process and
  keep nothing else running; if the detail LOD fails, ship overview and regional first (the viewers already fall back to the
  coarsest hillshade present).
- **Projection stretch.** LAEA centred at 10 E, 52 N stretches the North Cape and Ladoga by a few per cent; acceptable for
  context terrain, and the same projection the geology layers already use.
- **Two depth scales in one frame.** The shelf ramp runs out at 1,300 m and the Norwegian Sea basin is 3,000 m deep. The
  honest options are a frame-level `bathymetry: ocean` (coarser steps on the shelf) or a hybrid levels set with the ocean
  ramp. The viewers already carry both ramps; the decision is which key the story prints. Recommendation: ocean ramp with
  the shelf's 20 and 50 m steps kept, so the Dogger Bank and the Norwegian Trench still read.
- **Hillshade tone change** is a contract change for every consumer (`relief_layers` stays at 1; the PNG tone is not in the
  contract today). Writing the flat value into the manifest first, and only then changing the tone, keeps the old consumers
  working.
- **Size of release assets.** `atlantic` is 78 MB built; this frame will be similar. GitHub releases take it; Pages fetches
  it on each deploy, which has already timed out once for Bedrock at 100 MB. Publish overview and regional to Pages and
  keep detail in the release only.

## Acceptance

- Every named catchment in `source-to-sink` lies inside the frame (coverage check passes).
- `regional_hillshade.png` has flat ground at the stated tone, and a consumer that composites it with soft-light at full
  strength sees the Scottish Highlands, the Scandes and the Norwegian Trench without remapping.
- `zones.png` covers the frame and the budget's per-catchment temperature changes by less than 0.5 °C for catchments that
  were already inside `ne_europe`.
- The Pages site and the data release carry the frame with its attribution lines, and `docs/regions.md` lists it.
