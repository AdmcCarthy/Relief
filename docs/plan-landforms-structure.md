# Request: height windows for the structural analogues (measured analogues, loop D)

**Status 15 November 2026.** Written and built in the same session, on the owner's instruction to carry out loops A to E of
the study's own plan: `scripts/window.py dem` reads the Copernicus DEM GLO-90 one-degree tiles at their native cell
for any lon/lat box, mosaics them and writes one GeoTIFF in the local UTM zone with its provenance; fifteen windows are registered
in `regions/windows.json` under frame `dem`. Nothing is published: the windows are raw files under `data/raw/dem/windows/` and
are rebuilt by the command. No new source, no new frame, no change to the contract.

## Why height, and why outside the frames

The study adds two groups of settings to its register: **structure** (normal faults and scarps, half-grabens and tilted
blocks, rifts in plan, rift-flank uplift, salt diapirs and walls, inversion folds) and **the basin's elements** (foreland basins and
forebulges, shoreline geometry, shelf width and the shelf edge, clinoforms, strandplain width). A deposit is read from an optical
scene; structure is read from **height**: a scarp's height from profiles, a block's width from fault to fault, a fold's wavelength
from the spectrum of the surface, a forebulge from a long profile. The optical scene is the picture; the height grid is the
measurement.

The best living examples lie outside Relief's European frames: the Basin and Range, the East African Rift, the Red Sea margins, the
Zagros and the Great Kavir, the Ganges foreland. Relief's frames carry GLO-90 on land already (`regions/sources.json`
`cop_glo90`, verified, Copernicus licence, attribution recorded), so the source is known; what was missing was a way to read it for
a box with no frame.

## What was built

`scripts/window.py dem W S E N --name NAME [--cell 90]`, and `dem --all` for the registered windows. For each one-degree tile the
box touches, the COG is opened over HTTP (AWS open data, no sign-in), the tiles are merged in lon/lat over the box, and the mosaic is
reprojected once onto a UTM grid of the box centre's zone at the cell asked for (bilinear at the native cell, average when
decimated). The output carries `crs`, `cell_m`, `extent`, `lonlat_bounds`, `source`, `source_cell`, the tiles that did not exist
(all-sea tiles), `attribution`, `licence`, `built`, `valid_share` and the height range, as the EMODnet windows do. A consumer reads
the `.tif` and the `.json` beside it; the study reads them through its bathymetry reader with `region: dem` and `window: <name>`.

| Window | Centre | Box | Setting |
|---|---|---|---|
| `death_valley_dem` | 36.22 N, 116.93 W | 30 km | alluvial fan: radius from the apex to the break of slope |
| `batinah_dem` | 23.75 N, 57.65 E | 60 km | fan delta: the same |
| `wasatch_dem`, `corinth_dem` | 40.55 N, 111.85 W; 38.15 N, 22.5 E | 60 km | normal fault and scarp: scarp height, segment length and spacing |
| `tanganyika_dem`, `suez_dem` | 6 S, 29.8 E; 28.6 N, 33.3 E | 200, 120 km | half-graben: block width, asymmetry, crest-to-trough relief |
| `gregory_rift_dem`, `rhine_graben_dem` | 0.8 S, 36.1 E; 48.6 N, 8 E | 200, 150 km | rift in plan: rift width, segment length, transfer-zone spacing |
| `red_sea_flank_dem`, `western_ghats_dem` | 24.5 N, 36 E; 18.3 N, 73.6 E | 200, 150 km | rift-flank uplift: flank width, elevation profile, divide offset |
| `zagros_salt_dem`, `great_kavir_dem` | 27.5 N, 54 E; 34.7 N, 53.5 E | 120, 100 km | salt diapir and wall: diameter and spacing, wall length |
| `zagros_folds_dem`, `jura_dem` | 29.5 N, 51 E; 46.9 N, 6 E | 150, 100 km | inversion and fold: fold wavelength and amplitude, hinge length |
| `ganges_foreland_dem`, `po_plain_dem` | 25.5 N, 82 E; 44.6 N, 11 E | 400, 200 km | foreland and forebulge: basin width, bulge wavelength and amplitude |

The Ganges window is 400 km across, which at 90 m is 4,400 cells a side (78 MB float32): it is the one window that should be read
at `--cell 270` unless a profile at 90 m is needed, and the register says so by its size.

## What was not built, and why

- **Sea-floor windows outside Europe** (the Gulf of Mexico minibasins, the Arabian Gulf foreland, the Namibian and Sunda shelves,
  the Niger margin): EMODnet stops at Europe's edge and GEBCO 2024 at 15 arc-seconds is in Relief's plan but not yet an adapter for
  a window. The structural settings that need sea-floor data (salt minibasins, the Arabian Gulf's forebulge) keep their land
  examples first; a GEBCO window adapter is the next request if those scenes are wanted.
- **GLO-30**: three times finer, some countries' tiles withheld. GLO-90 resolves a scarp of tens of metres and a fold of kilometres;
  a 30 m window is a change of one constant in `dem_window` if a scene needs it.
- **Shading and base tints** for these windows: Relief ships none at this cell and the consumer draws none (its rule). The DEM
  windows are measured, and shown as a height ramp of Relief's land scale by the consumer, who says so.

## Sources and licence

Nothing new: Copernicus DEM GLO-90, © DLR e.V. 2010–2014 and © Airbus 2014–2018, provided under COPERNICUS by the European Union and
ESA; recorded in `docs/sources.md` and Idiom's `DATASETS.md` already. Heights are on EGM2008.

## Acceptance

- A window's `.json` carries cell, CRS, extent, attribution and the tiles that did not exist; `valid_share` is above 0.95 on a land box.
- The Death Valley window's apex-to-toe profile of a Panamint fan falls from about 1,000 m to the playa at about −80 m over 8 to 10 km,
  which is the published order of the fans' radius; the study checks it against its own fan method.
