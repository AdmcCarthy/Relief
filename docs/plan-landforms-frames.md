# Request: sea-floor frames for the measured analogues (ep-landforms)

**Status 15 November 2026.** Steps 1 to 6 done on the owner's go-ahead. `med_west` is registered (1,190 x 1,020 km, EPSG:3035, a little larger than
estimated because the box corners spread in LAEA), fetched with `build_hires.py` (GLO-90, EMODnet 2024, ETOPO 2022; EMODnet gives 99 % of the sea),
merged at 120 m (9,917 x 8,500), and built: three LODs (2,000, 900, 300 m), a six-level tile pyramid down to 120 m (469 tiles), a 400 m single texture inside the 10 MB budget, base tints; 88 MB in `data/out/med_west`. Its coverage
check is new: `regions.py check` now reads a `points` block (eight named places, 20 km inside the edge), and `regions.py check` no longer
needs the Sodir raw files on the machine (it keeps the last report for those keys). `scripts/window.py` and `regions/windows.json` write the five
windows (Norfolk Banks, Flemish Banks, Celtic Sea ridges, Var canyon, Rhône channel) at 115 m. Step 5 needed nothing: `barents_sea` (merged 0.0083 degrees, hires 400 m) and `atlantic`
(hires 2,000 m, no merged file) had been restored on 14 November. Nothing is published: the `med_west` layers and windows wait for a release.

Two findings against the plan. (1) The Var canyon profile read from the 120 m `med_west` grid and from the 115 m window agree to within 1 % in
depth and width; the plan's test against "the detail grid" (300 m) was not run because the 300 m level is a contour layer, not a grid. (2) The Norfolk
window shows crest-to-trough relief (1st to 99th percentile of local relief) of about 17 m; the 15 arc-second merged grid gives about 19 m, so
it is not a smear in amplitude, only in cell size (270 x 165 m against 115 m). Read widths from the window; read heights from either.

Written 14 November 2026 at the owner's request, as a plan and not a build: nothing in the sections below had been fetched or run when it was written. The private
repo `ep-landforms` measures the plan-view dimensions of modern depositional settings, and reads the submerged ones (tidal
sand ridges, shelf edges, canyons and channel-levee systems, fans, slides, glacial troughs) from depth grids rather than optical
imagery. It takes those grids through Relief and never contours, shades or resamples terrain itself. Two things stop it today.

## What ep-landforms reads, and what it finds

| Scene (setting) | Centre | Box | Frame today | Grid held | What the grid can and cannot give |
|---|---|---|---|---|---|
| Norfolk Banks (tidal sand ridges) | 53.2 N, 1.9 E | 80 km | `north_sea_wide` | merged 15 arc-second (about 270 x 460 m) | ridge length and spacing; not ridge width or height (ridges are 1 to 3 km wide, 10 to 40 m high) |
| Flemish Banks (tidal sand ridges) | 51.4 N, 2.6 E | 60 km | `ne_europe_wide` | merged 15 arc-second | as above |
| Celtic Sea ridges | 49.5 N, 7.5 W | 150 km | `ne_europe_wide` | merged 15 arc-second | length, spacing, orientation; height only roughly |
| Møre shelf edge (clinoform) | 63.6 N, 4.5 E | 200 km | `norwegian_sea_wide` | merged 15 arc-second | shelf-edge depth, slope, relief: adequate |
| Storegga, Trænadjupet (slides) | 64.3 N, 3.5 E; 67 N, 8 E | 300, 200 km | `norwegian_sea_wide` | merged 15 arc-second | headwall, run-out, area: adequate |
| Norwegian Channel (glacial trough) | 58.5 N, 5 E | 300 km | `north_sea_wide` | merged 15 arc-second | adequate |
| Bear Island Fan, Hinlopen Slide | 72.5 N, 14.5 E; 80.7 N, 16.5 E | 500, 200 km | `barents_sea` | **no grid on this machine** (release asset) | adequate once fetched |
| Congo canyon and fan | 6 S, 10 E | 300, 600 km | `atlantic` | **no grid on this machine**; ETOPO at 1 arc-minute | course and area; never a channel width |
| Gulf of Lion shelf edge and canyons | 42.8 N, 4 E | 150 km | `europe_s2s` | hires 1,600 m (EPSG:3035) | the break as a line; no canyon width |
| Var canyon and channel | 43.5 N, 7.4 E | 60 km | `europe_s2s` | 1,600 m | the canyon exists; nothing measurable |
| Rhône channel, Neofan and fan | 42.3 N, 5 E; 42 N, 5.5 E | 150, 300 km | `europe_s2s` | 1,600 m | fan area and aspect only |
| Nile fan | 32.5 N, 31 E | 300 km | `europe_s2s` | 1,600 m | fan area and aspect only |

Two gaps follow.

1. **No frame holds the Mediterranean at a cell that resolves a canyon or a channel.** EMODnet Bathymetry 2024 covers the whole
   Mediterranean at its native 1/16 arc-minute (about 115 m), and the Var canyon (2 to 5 km wide, 300 to 600 m deep), the Rhône
   deep-sea channel (1 to 3 km wide, levees tens of metres high) and the Gulf of Lion canyons are the only European examples of a
   river-fed deep-marine system at the scale of the Paleocene fans of the North Sea.
2. **The European frames' merged grids are at 15 arc-seconds, not at EMODnet's 115 m**, so a tidal ridge's width and height, which
   are the measures a shelf-sand analogue needs, cannot be read from them. Relief's `build_hires.py` already fetches EMODnet decimated
   to a chosen cell for a region; what is missing is a product at (or near) the native cell for a few small windows.

## Proposal

**A. A western Mediterranean frame, `med_west`.**

| | Proposal |
|---|---|
| `id` | `med_west` |
| CRS | ETRS89 / LAEA Europe, EPSG:3035, so it nests with `ne_europe` and `europe_s2s` and consumers' transforms carry over; or UTM 31N (EPSG:25831) if a conformal frame is preferred for the Rhône and Var at 3 to 8 E |
| `design.lonlat_box` | `[-1.0, 36.0, 12.0, 44.5]`, `fit: outer`: the Balearic and Ligurian basins, the Gulf of Lion, the Rhône fan, the Var, the Ebro margin, Corsica and Sardinia |
| `bathymetry` | `ocean` (the Balearic abyssal plain is 2,800 m) with the shelf's 20, 50 and 100 m steps kept, as `europe_s2s` does |
| `fetch.step_deg` | 0.001042 (1/16 arc-minute, EMODnet native) for the sea; Copernicus GLO-90 for the land as the other frames |
| `lods` | overview 2,000 m, regional 900 m, detail 300 m, as `north_sea`; a fourth `fine` level at 120 m for the tile pyramid only, if the memory allows |
| Size | about 1,150 x 950 km; the raw EMODnet fetch at 115 m is about 10,000 x 8,300 cells (330 MB float32), so the fetch must be boxed and decimated as `build_hires.py` does, and the 120 m level built one window at a time |

A Nile scene would need the eastern basin (`med_east`, 20 to 36 E, 30 to 37 N) and is the lesser need: the Nile fan is mud-rich and
measured only at lobe scale.

**B. Fine windows at EMODnet's native cell for the measured sea-floor scenes.** Not a frame: a `hires` product per scene window in
the existing frames, written with `build_hires.py run <frame> --cell 115` restricted to a lon/lat box, or a small new entry point
`scripts/window.py <frame> <west> <south> <east> <north> --cell 115` that writes `data/raw/<frame>/windows/<name>.tif` with its
provenance JSON and attribution. The windows: Norfolk Banks (80 km), Flemish Banks (60 km), Celtic Sea ridges (150 km), and, if the
`med_west` frame is built, the Var and Rhône channel boxes. Five windows of 100 x 60 km at 115 m are about 500,000 cells each, a few
megabytes: no disk or release concern. `ep-landforms` would read these files as it reads `merged.tif` today, with the cell size
recorded.

**C. Fetch the `barents_sea` and `atlantic` merged grids** on this machine from the `grids-*` release (`scripts/fetch_data.py --grids
barents_sea atlantic`), so the Bear Island Fan, Hinlopen and Congo scenes read. This is a download of Relief's own release assets and
needs only the go-ahead.

## What ep-landforms does meanwhile

It reads the 15 arc-second grids where they are, records the cell size in metres on every scene and limits its measures to what
the cell supports (ridge length and spacing, not width and height; fan area, not channel width), and says so on the slide. The
Mediterranean scenes are kept in its register with a `resolution` note and are not measured until A or B exists.

## Sources and licence

Nothing new: EMODnet Bathymetry 2024 (free with attribution), Copernicus DEM GLO-90, GEBCO or ETOPO beyond the EMODnet edge, all
in `docs/sources.md` and Idiom `DATASETS.md`. The Mediterranean frame adds no source, only an extent.

## Work, in order, if agreed

1. Register `med_west` in `regions/regions.json`, `regions.py sync`, a coverage check that the Var and Rhône canyon heads and the
   Gulf of Lion shelf edge lie inside. Half a day.
2. `build_hires.py plan med_west` to list the EMODnet tiles and their size; no fetch until the owner says so. One hour.
3. Fetch and build the three standard LODs, then the 120 m tile level one window at a time; base tints; release. Half a day of
   machine time, run alone for memory.
4. The window entry point (B) and the five windows. Half a day.
5. `fetch_data.py --grids barents_sea atlantic` (C). Minutes.
6. `docs/regions.md`, `docs/data-releases.md` and Idiom `DATASETS.md` updated; `ep-landforms` points its Mediterranean scenes at
   the new frame and its ridge scenes at the windows.

## Acceptance

- A profile across the Var canyon read from the `med_west` detail grid gives a width and depth within 10 per cent of the 120 m
  window's; the Norfolk Banks window shows ridge crests 10 to 40 m above the troughs where the 15 arc-second grid shows a smear.
- Every new product carries its cell size and attribution in its JSON, as `hires.json` does today.
