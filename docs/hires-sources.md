# Better-resolution data for the regions

Researched 2026-11-08. **Nothing here has been downloaded or processed.** The machine-readable version is
[`regions/sources.json`](../regions/sources.json); the processing is [`scripts/build_hires.py`](../scripts/build_hires.py),
which plans before it fetches and only runs on an explicit `run` command.

House style for every example: **Detuned, stepped relief (by climate zone), linear bathymetry, no contours, no
illumination.**

## The short answer

| Region | Biggest real gain | Source | Resolution change |
|---|---|---|---|
| Barents Sea | Sea east of 43 E and north of Svalbard | IBCAO v5.0 (manual download) | 1.8 km (ETOPO) → **100 m** |
| Barents Sea | Svalbard land | NPI Svalbard DTM 20, or ArcticDEM 32 m | 90 m → **20 to 32 m** |
| Norwegian Sea, North Sea, Barents | Norwegian shelf and banks | Kartverket sea-floor model 25 m (MAREANO) and 50 m | 115 m → **25 to 50 m** |
| World | Whole map | GEBCO_2026 (manual download) | ETOPO sampled every 5th cell → **450 m averaged properly** |
| All land | Everywhere | Copernicus GLO-30 | 90 m → **30 m** |
| North Sea, Norwegian Sea | Norwegian land | Kartverket seamless terrain WCS (0.25 to 1 m lidar mosaic) | 90 m → **metre scale** |
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
| [NPI Svalbard DTM 20](https://geonorge.no/geonetworktest/srv/api/records/9d118d31-182c-495b-b7be-d819cc7444b1) (also DTM 5, 50) | 20 m | Svalbard | Geonorge download API; one area for the archipelago | open (NPI); exact wording to confirm | capabilities answered |
| Kartverket seamless terrain WCS (`wcs.hoyde-dtm_somlos`, coverage `las_dtm`) | 0.25 m grid, 0.25 to 1 m data | mainland Norway | WCS 2.0.1, EPSG:25833 | open (Kartverket); CC BY 4.0 not confirmed | capabilities and DescribeCoverage answered; **scaling not tested** |
| Kartverket DTM 10 (historic annual versions, UTM 32/33/35) | 10 m | mainland Norway | Geonorge download, map-sheet areas | open; Kartverket now points to hoydedata.no | UTM 32 capabilities answered; sheets cannot be chosen without outlines |
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
| Kartverket sea-floor model **25 m** (MAREANO) | 25 m | outside 12 nm; Møre to Finnmark, east Barents, parts around Svalbard | Geonorge download, 1,085 half-degree cells | open; CC BY 4.0 to confirm | capabilities answered |
| Kartverket sea-floor model 50 m | 50 m | Norwegian waters | Geonorge download (already scripted) | CC BY 4.0 | in use for Vestland |
| [IBCAO v5.0](https://doi.org/10.17043/ibcao-5.0) | 100 m | Arctic Ocean incl. Barents, Svalbard | four GeoTIFFs, polar stereographic | open; terms on the GEBCO page, not for navigation | **manual** download |
| [GEBCO_2026](https://www.gebco.net/data-products-gridded-bathymetry-data/gebco2026-grid) | 450 m | global | 7 GB NetCDF or 8 GeoTIFF tiles; the download app cuts a user-defined area | public domain, acknowledge GEBCO, not for navigation | **manual** download |
| Denmark's Depth Model 2024 | 50 m | Danish EEZ | GeoTIFF or web service, free Dataforsyningen account | free incl. commercial, not for navigation | manual; `seabed.py` already reads it |
| BSH seabed DTM | 50 m (1 m on request, maybe for a fee) | German North Sea and Baltic | GeoSeaPortal (no API found) | free under GeoZG; licence name not found | manual |
| UKHO ADMIRALTY Marine Data Portal | survey dependent | UK waters | portal; outlines as GeoJSON, KML, Shapefile; gridded download **not confirmed** | UKHO Bathymetry Data Licence (OGL plus not-for-navigation) | not scriptable |
| BSBD 0.9.x (Baltic) | 500 m | Baltic Sea | BSHC page | CC BY 3.0 plus extra terms | not needed: EMODnet contains it |
| NOAA ETOPO 2022 (current fallback) | 1.8 km | global | OPeNDAP, about 0.5 MB/s | public domain | in use |

EMODnet's own release cadence is about two years (2018 first, 2024 latest), so a 2026 release is plausible; I found
no announcement. EMODnet also lists "high-resolution snapshots" (1/32 to 1/512 arc-minute, about 60 m to 4 m) for some
areas; I could not find which areas or a way to fetch them, so they are not planned.

## Per region

- **North Sea**: land Kartverket seamless WCS then OS Terrain 50 then GLO-30/90; sea Kartverket 25/50 m, Danish and
  German 50 m (manual), EMODnet, ETOPO. Gain: Norwegian shelf edge and fjord mouths.
- **Norwegian Sea**: land Kartverket WCS, GLO-30/90; sea MAREANO 25 m, Kartverket 50 m, EMODnet. Gain: shelf, banks,
  Storegga area, Nordland coast.
- **Barents Sea**: land NPI Svalbard 20 m, Kartverket WCS, ArcticDEM 32 m, GLO-30/90; sea Kartverket 25/50 m, IBCAO v5,
  EMODnet, GEBCO 2026, ETOPO. The largest improvement of any region; no source for the Russian shelf finer than IBCAO
  and GEBCO.
- **NE Europe**: land GLO-30 then OS Terrain 50; sea EMODnet with Danish and German 50 m in their waters and
  Kartverket 50 m for the Norwegian sector. Modest.
- **World**: GEBCO 2026 (land and sea), ETOPO fallback.

## Running it

```
uv run python scripts/build_hires.py plan                    # all regions: what runs, what is skipped and why (no network)
uv run python scripts/build_hires.py plan barents_sea --include-unverified
uv run python scripts/build_hires.py run north_sea --stage fetch     # hours; resumable (hires/<source>/DONE.json)
uv run python scripts/build_hires.py run north_sea --stage merge     # -> data/raw/north_sea/hires.tif + hires.json
uv run python scripts/build_hires.py run north_sea --stage render    # -> data/out/north_sea/demo/ (page assets)
uv run python scripts/render_region.py north_sea --source current    # first-pass assets, what the page shows today
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

- **Kartverket seamless WCS scaling.** The service answers and reports a 0.25 m grid, but whether it resamples on request
  (SCALESIZE) or refuses large requests is untested. The script tests this on its first request and drops the source if
  it fails, falling back to GLO-30. The older DTM 10 would then need a manual order.
- **GEBCO Cloud Optimized GeoTIFF.** A 4.4 GB COG of GEBCO_2026 is listed on Source Cooperative, but I could not find its
  object URL, so GEBCO is a manual download. If it is reachable, a windowed read would remove the manual step.
- **Licence wording** for Kartverket's 25 m model and DTM 10, the NPI models, BSH and IBCAO: all described as open, none
  confirmed as a named licence. Check each Geonorge or provider record before publishing derived tiles at full resolution.
- **ArcticDEM tile coverage** over Novaya Zemlya and Svalbard (the index files list it; I did not read them), and whether
  its surface heights are better than GLO over the ice caps.
- **UK, German, Polish, Dutch and Danish land and sea models** beyond what is in the tables: only the UK 50 m and the
  Danish and German sea models were checked, and the latter two have no API.
- **Download sizes and times** for the Geonorge orders and the ArcticDEM window are not measured; the EMODnet chunk fetch
  took about 5 to 7 minutes per region at the first-pass resolution.
