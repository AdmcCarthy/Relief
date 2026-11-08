# Better-resolution data for the regions

Researched 2026-11-08. **Status 2026-11-08: researched, then run** (see 'Run results' at the end). The machine-readable version is
[`regions/sources.json`](../regions/sources.json); the processing is [`scripts/build_hires.py`](../scripts/build_hires.py),
which plans before it fetches and only runs on an explicit `run` command; tiles are cut by [`scripts/build_tiles.py`](../scripts/build_tiles.py) and shown on the zoom page.

House style for every example: **Detuned, stepped relief (by climate zone), linear bathymetry, no contours, no
illumination.**

## The short answer

| Region | Biggest real gain | Source | Resolution change |
|---|---|---|---|
| Barents Sea | Sea east of 43 E and north of Svalbard | IBCAO v5.0 (manual download) | 1.8 km (ETOPO) → **100 m** |
| Barents Sea | Svalbard land | NPI Svalbard DTM 20, or ArcticDEM 32 m | 90 m → **20 to 32 m** |
| Norwegian Sea, North Sea, Barents | Norwegian shelf and banks | Kartverket sea-floor model 25 m (MAREANO) and 50 m | 115 m → **25 to 50 m** |
| World | Whole map | ETOPO 2022 averaged 3 × 3 (GEBCO 2026 is available but adds nothing at a 5 km cell) | ETOPO sampled every 5th cell → **averaged properly** |
| Atlantic | Spreading ridges, fracture zones | GEBCO 2026, scripted from CEDA tiles | ETOPO 1.85 km → **463 m source**; measured gain 3 to 6 % small-scale relief |
| All land | Everywhere | Copernicus GLO-30 | 90 m → **30 m** |
| North Sea, Norwegian Sea | Norwegian land | *not available*: Kartverket's lidar terrain service is under the Norge digitalt licence (partners only), so it cannot be published | stays Copernicus GLO-30 |
| NE Europe | Little | GLO-30, Danish and German 50 m models in their waters | already finer than the picture |

## What resolution can the page show

This is the constraint that decides how much of the above shows up. Each region example is **one elevation texture**:
about 8,192 px a side at most, and about 10 MB as lossless 16-bit WebP (Vestland is 0.9 byte per pixel). For a whole
region that fixes the cell size, whatever the source resolution:

| Region | Frame | Drawn now | Planned web cell | Pixels | Native source finer than the cell? |
|---|---|---|---|---|---|
| North Sea | 740 × 880 km | 500 m | 250 m | 2,960 × 3,520 | yes, by 2 to 10× |
| Norwegian Sea | 1,070 × 1,000 km | 500 m | 400 m | 2,675 × 2,500 | yes |
| Barents Sea | 2,150 × 1,800 km | 1 km | 600 m | 3,584 × 3,000 | yes |
| NE Europe | 2,270 × 1,580 km | 1 km | 600 m | 3,784 × 2,634 | yes (GLO-30 and EMODnet already) |
| World | 34,488 × 16,786 km | 10 km | 8 km | 4,311 × 2,099 | yes |

Two consequences:

1. **A finer source only changes the picture where the current source is coarser than the cell**: the Arctic sea
   (ETOPO), the world (ETOPO sampled), and anywhere EMODnet is itself interpolated from sparse surveys. At a 250 to
   600 m cell, GLO-30 and a 1 m lidar model look the same once averaged. Their value is in zoomed views, and in cleaner
   averaging at the coast and in fjords.
2. **To use 10 to 50 m data for real, delivery has to change**: tiled elevation (for example 1,024 px tiles of 16-bit
   WebP in a zoom pyramid, or terrain PMTiles) so the browser fetches only what is in view. That is the natural next
   step after this one, and `build_hires.py` already produces the merged grid it would be cut from; use `--cell 50`
   for a regional grid, then tile it.

Sea-floor seams are visible in the current examples (for example straight edges in deep water in the North Sea and
Norwegian Sea): EMODnet composites survey blocks and fills the gaps from coarser grids. Better surveys at the shelf
edge (Kartverket 25 and 50 m) and a better deep-water base (GEBCO 2026, IBCAO 5) are what remove them.

## Land (relief)

| Source | Res. | Covers | Access | Licence | Checked |
|---|---|---|---|---|---|
| [Copernicus DEM GLO-30](https://registry.opendata.aws/copernicus-dem/) | 30 m | global | 1° COG tiles on open AWS (`copernicus-dem-30m`); overviews make coarse reads cheap | free for the general public; the bucket readme links an older annex, so check the current one | tile URL answered |
| Copernicus GLO-90 (current) | 90 m | global | as above | as above | in use |
| [ArcticDEM mosaic v4.1](https://registry.opendata.aws/pgc-arcticdem) | 2, 10, 32 m | north of about 60 N | COG tiles plus VRT index on open S3 (`pgc-opendata-dems`) | CC BY 4.0, PGC acknowledgement | 10 m and 32 m VRT answered |
| [NPI Svalbard DTM 20](https://geonorge.no/geonetworktest/srv/api/records/9d118d31-182c-495b-b7be-d819cc7444b1) (also DTM 5, 50) | 20 m | Svalbard | Geonorge download API; one area for the archipelago | **CC BY 4.0** (record 9d118d31…) | capabilities answered |
| ~~Kartverket seamless terrain WCS~~ (`wcs.hoyde-dtm_somlos`) | 0.25 m grid | mainland Norway | ArcGIS WCS (WCS 1.0.0 width/height resamples) | **Norge digitalt licence, access limited to partners** (Geonorge record 311782b2…): **excluded** | worked technically and was used for a first build, then removed |
| Kartverket DTM 10 (historic annual versions, UTM 32/33/35) | 10 m | mainland Norway | Geonorge download, map-sheet areas | **CC BY 4.0** (record dddbb667…), 2013 data; Kartverket now points to hoydedata.no | UTM 32 capabilities answered; sheets cannot be chosen without outlines |
| [OS Terrain 50](https://docs.os.uk/os-downloads/products/land-and-terrain-portfolio/os-terrain-50) | 50 m | Great Britain incl. Shetland | OS Downloads API, no key; ASCII grid zip, 162 MB | OS OpenData (OGL) | download list answered |
| Germany DGM25 / DGM10 (state level) | 25 / 10 m | Germany | state ATOM services | dl-de/by-2.0 in the state records seen; federal status unclear | not scripted |
| Poland NMT (GUGiK) | 1 m, 5 m | Poland | WCS (addresses on geoportal.gov.pl); request size limited | free for any use; licence name not found | not scripted |
| Netherlands AHN, Denmark DHM | 0.5 m, 0.4 m | NL, DK | not researched in detail | open | not scripted |

Notes: GLO-30 and ArcticDEM are **surface** models (trees, buildings, glacier surfaces); Kartverket's seamless WCS and
OS Terrain are bare-earth. At a 250 m cell the difference does not show. German, Polish, Dutch and Danish land models
were left out on purpose: at a 600 m NE Europe cell they add nothing visible.

## Sea floor (bathymetry)

| Source | Res. | Covers | Access | Licence | Checked |
|---|---|---|---|---|---|
| EMODnet Bathymetry DTM 2024 (current) | 115 m | European seas, 11 N to 90 N, 70.5 W to 43 E | WCS; 2° chunks only, no scaling | open; cite EMODnet | in use |
| Kartverket sea-floor model **25 m** (MAREANO) | 25 m | outside 12 nm; Møre to Finnmark, east Barents, parts around Svalbard | Geonorge download, 1,085 half-degree cells | **CC BY 4.0** (record 39e022aa…) | capabilities answered |
| Kartverket sea-floor model 50 m | 50 m | Norwegian waters | Geonorge download (already scripted) | CC BY 4.0 | in use for Vestland |
| IBCAO v5.2 (2026; v5.0 doi:10.17043/ibcao-5.0) | 100, 200, 400 m | Arctic Ocean incl. Barents, Svalbard | CEDA zips: 100 m is 12 GB, 200 m 3 GB, **400 m 776 MB** (deflated: no windowed reads). Script streams the 400 m zip, clips to the region and deletes it | open; terms on the GEBCO page, not for navigation | zip sizes and range support answered |
| [GEBCO_2026](https://www.gebco.net/data-products-gridded-bathymetry-data/gebco2026-grid) | 450 m | global | **eight 90° GeoTIFF tiles served unzipped on CEDA (int16, uncompressed, 933 MB, range requests)**; also 4.2 GB zip and NetCDF | public domain, acknowledge GEBCO, not for navigation | **scripted** (`remote_tiles`): read in bands, averaged on arrival, nothing stored; used for the Atlantic |
| Denmark's Depth Model 2024 | 50 m | Danish EEZ | GeoTIFF or web service, free Dataforsyningen account | free incl. commercial, not for navigation | manual; `seabed.py` already reads it |
| BSH seabed DTM | 50 m (1 m on request, maybe for a fee) | German North Sea and Baltic | GeoSeaPortal (no API found) | free under GeoZG; licence name not found | manual |
| UKHO ADMIRALTY Marine Data Portal | survey dependent | UK waters | portal; outlines as GeoJSON, KML, Shapefile; gridded download **not confirmed** | UKHO Bathymetry Data Licence (OGL plus not-for-navigation) | not scriptable |
| BSBD 0.9.x (Baltic) | 500 m | Baltic Sea | BSHC page | CC BY 3.0 plus extra terms | not needed: EMODnet contains it |
| NOAA ETOPO 2022 (current fallback) | 1.8 km | global | OPeNDAP, about 0.5 MB/s | public domain | in use |

EMODnet's own release cadence is about two years (2018 first, 2024 latest), so a 2026 release is plausible; I found
no announcement. EMODnet also lists "high-resolution snapshots" (1/32 to 1/512 arc-minute, about 60 m to 4 m) for some
areas; I could not find which areas or a way to fetch them, so they are not planned.

## Per region

- **North Sea**: land OS Terrain 50 then GLO-30/90; sea Kartverket 25/50 m, Danish and
  German 50 m (manual), EMODnet, ETOPO. Gain: Norwegian shelf edge and fjord mouths.
- **Norwegian Sea**: land GLO-30/90; sea MAREANO 25 m, Kartverket 50 m, EMODnet. Gain: shelf, banks,
  Storegga area, Nordland coast.
- **Barents Sea**: land NPI Svalbard 20 m, GLO-30/90 (ArcticDEM 32 m not used); sea Kartverket 25/50 m, IBCAO v5,
  EMODnet, ETOPO. The largest improvement of any region; no source for the Russian shelf finer than IBCAO.
- **NE Europe**: land GLO-30 then OS Terrain 50; sea EMODnet with Danish and German 50 m in their waters and
  Kartverket 50 m for the Norwegian sector. Modest.
- **World**: ETOPO 2022 averaged (GEBCO 2026 is scripted but not needed at 5 km).
- **Atlantic**: GEBCO 2026 alone (global coverage), 2 km grid.

## Tiles: showing the fine data

`scripts/build_tiles.py <region>` cuts a region's grid (the `hires.tif` from the build, or the first-pass grid) into a
power-of-two pyramid of 512 px lossless 16-bit WebP tiles under `data/out/<region>/tiles/`, with a `tiles.json`
describing every level. The zoom page (`explore.html`) picks the level that matches the zoom, fetches only the tiles in
view, stitches them into one texture and draws it with the same Detuned style, so a 150 m grid is as cheap to browse as a
2 km one. Tiles are the committed deliverable; `data/raw` stays ignored.

## Running it

```
uv run python scripts/build_hires.py plan                    # all regions: what runs, what is skipped and why (no network)
uv run python scripts/build_hires.py plan barents_sea --include-unverified
uv run python scripts/build_hires.py run north_sea --stage fetch     # hours; resumable (hires/<source>/DONE.json)
uv run python scripts/build_hires.py run north_sea --stage merge     # -> data/raw/north_sea/hires.tif + hires.json
uv run python scripts/build_hires.py run north_sea --stage render    # -> data/out/north_sea/demo/ (page assets)
uv run python scripts/render_region.py north_sea --source current    # first-pass assets (single texture) from the coarse grid
uv run python scripts/build_tiles.py north_sea                       # tile pyramid from hires.tif -> data/out/north_sea/tiles/
```

- Each fetch adapter decimates to the target cell as it reads (COG overviews, averaged WCS chunks, averaged Geonorge
  cells), so full-resolution data never sits on disk; the disk is 10 GB.
- A source that fails (an endpoint down, the Kartverket WCS refusing scaled requests) is logged and skipped; the next one
  in the region's list fills in. Re-running picks up where it stopped.
- Manual sources: drop GeoTIFFs in `data/raw/<region>/manual/<source id>/` and they are used on the next merge.
- `render` refuses nothing but warns if a texture exceeds 8,192 px or the web budget.
- Quality checks (`tests/test_hires.py`): the plan is consistent, every list ends in a source that covers the region,
  blending prefers the finer source and ramps across seams, assets stay within budget.

## What I could not confirm

- **GEBCO Cloud Optimized GeoTIFF on Source Cooperative**: its object URL was never found; not needed, since CEDA serves the
  eight GeoTIFF tiles directly (above).
- **Licence wording** for Kartverket's 25 m model and DTM 10, the NPI models, BSH and IBCAO: all described as open, none
  confirmed as a named licence. Check each Geonorge or provider record before publishing derived tiles at full resolution.
- **ArcticDEM tile coverage** over Novaya Zemlya and Svalbard (the index files list it; I did not read them), and whether
  its surface heights are better than GLO over the ice caps.
- **UK, German, Polish, Dutch and Danish land and sea models** beyond what is in the tables: only the UK 50 m and the
  Danish and German sea models were checked, and the latter two have no API.
- **Download sizes and times** for the Geonorge orders and the ArcticDEM window are not measured; the EMODnet chunk fetch
  took about 5 to 7 minutes per region at the first-pass resolution.

## Licences checked before publishing (2026-11-08)

CC BY 4.0: Kartverket sea floor 25 m and 50 m, NPI Svalbard DTM 20, Kartverket DTM 10 (historic). Open Government Licence v3:
IBCAO v5.2 (cite as on the CEDA record), OS Terrain 50. Copernicus DEM: free for the general public with the Copernicus
attribution. EMODnet: open, cite the consortium. ETOPO: public domain. Köppen-Geiger (Beck et al. 2023): CC BY 4.0.
**Not redistributable: the Kartverket seamless terrain WCS (Norge digitalt licence).**

## Run results (2026-11-08)

`build_hires.py run` was run for all five regions (fetch, merge, then `render_region.py` and `build_tiles.py`), at these
grid cells: North Sea 150 m, Norwegian Sea 250 m, Barents Sea 400 m, NE Europe 400 m, world 5 km. Each tile pyramid is
5 levels, 15 to 31 MB.

| Region | Land sources used | Sea share by source |
|---|---|---|
| North Sea | OS Terrain 50, GLO-30, GLO-90 | EMODnet 85 %, Kartverket 50 m 10 %, Kartverket 25 m 4 %, ETOPO 1 % |
| Norwegian Sea | GLO-30, GLO-90 | EMODnet 68 %, Kartverket 50 m 18 %, Kartverket 25 m 14 % |
| Barents Sea | NPI Svalbard 20 m, GLO-30, GLO-90 | EMODnet 47 %, **IBCAO 39 %**, Kartverket 25 m 7 %, 50 m 6 % |
| NE Europe | GLO-30, OS Terrain 50, GLO-90 | EMODnet 94 %, Kartverket 50 m 4 % (Danish and German models not supplied) |
| World | ETOPO 2022 averaged 3 x 3 | ETOPO (GEBCO not used: see below) |

What happened that differs from the plan:

- **The Kartverket seamless terrain service was used, then removed.** It fetched and merged well (and returns exact 0 outside
  Norway, which had to be masked), but its Geonorge record is under the Norge digitalt licence, limited to partners, so tiles
  derived from it cannot be published. The three Norwegian regions were rebuilt on open sources only; the Norwegian land is
  GLO-30 again. The open alternatives are DTM 10 or DTM 1 from hoydedata.no (CC BY 4.0), which need their map sheets chosen.
- **Priority order matters.** IBCAO (400 m) first overwrote EMODnet (115 m) over most of the Barents Sea; EMODnet now
  outranks it, so IBCAO supplies only the east and the far north. A test guards the order.
- **OS Terrain 50 is a zip of zips**, one per 10 km tile named by grid reference; the first run found no tiles. Fixed, and
  the North Sea and NE Europe re-merged.
- **ArcticDEM was not used.** Reading its 32 m VRT for the whole Barents window ran 15 minutes at near-zero CPU
  (sequential HTTP over about 900 tiles) with little to gain at a 400 m cell; it was stopped. A tile-parallel reader would
  fix it if the ice-cap heights matter.
- **IBCAO v5.2 at 400 m**, not 100 m: the 100 m zip is 12 GB. The 400 m zip (776 MB) is streamed, clipped and deleted.
- **GEBCO was not used for the world.** At a 5 km world cell, ETOPO 2022 averaged properly (3 x 3 on its 1.85 km grid) shows the
  same picture. The world is the same data as before, averaged instead of sampled. (GEBCO is used for the Atlantic: see the end.)
- **Merge speed**: warping each piece into only its own window cut the Barents merge from over 11 minutes to under 2.
- **One stall**: an EMODnet chunk request hung for three hours with no progress; read timeouts are now 15 s connect and 90 s
  read, and a re-run resumed from the finished sources.
- Elapsed times: Kartverket sea orders 10 to 20 minutes per region, EMODnet chunks 5 to 10 minutes, ETOPO for the world
  about 25 minutes, merges 2 to 3 minutes.

### GEBCO 2026 for the Atlantic (added later the same day)

The `remote_tiles` adapter reads GEBCO's CEDA tiles in bands of rows with four threads (61 bands, about 5 GB of transfer, 8
minutes), averages them to 2 km and keeps only the result; the Atlantic merge takes under a minute and about 600 MB. Memory
was the constraint: a 1.5 km Atlantic grid is 79 million cells, which this machine could not merge, so the grid is 2 km (44
million), and the merge skips the feathering pass for a layer with nothing beneath it. Effect: small-scale deep-ocean relief
3 to 6 % higher than the ETOPO version, visually similar: see [depth-scale.md](depth-scale.md). GEBCO is not used for the world
(5 km) or the Barents Sea, where the existing sources already match the cell.
