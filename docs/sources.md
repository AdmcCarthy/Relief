# Open sources

Checked 2026-11-07. Keep the attribution lines with any map made from these data.

| Use | Dataset | Resolution | Coverage | Access | Licence / terms | Status here |
|---|---|---|---|---|---|---|
| Sea floor (primary, Europe) | **EMODnet Digital Bathymetry DTM 2024** | 1/16 arc-minute (~115 m) | European seas incl. North Sea, Norwegian Sea, Barents Sea | WCS `ows.emodnet-bathymetry.eu/wcs` (coverage `emodnet__mean`), or 59 tiles (GeoTIFF, NetCDF, ASCII) | Open access; attribution "EMODnet Bathymetry Consortium (2024): EMODnet Digital Bathymetry (DTM)". Check each tile's metadata licence: some contributing surveys are not open data in raw form | **Used** (WCS box cut) |
| World, and sea outside EMODnet (east of 43 E) | **NOAA NCEI ETOPO 2022** surface elevation | 60 arc-second (~1.8 km) | Global | THREDDS OPeNDAP `ngdc.noaa.gov` (slow, about 0.5 MB/s: windows only) | Public domain; cite NOAA NCEI (2022) ETOPO 2022 15 Arc-Second Global Relief Model | **Used** (`fetch_region.py`) |
| Coverage checks | **Sodir FactMaps** blocks (layer 802) and fields (layer 502); **EMODnet Human Activities** hydrocarbon wells and platforms | outlines, points | Norwegian shelf; European offshore | `scripts/fetch_sodir.py`; EMODnet WFS `ows.emodnet-humanactivities.eu` | NLOD (Sodir); EMODnet open | **Used** for `regions/coverage.json` only, not drawn |
| Sea floor (global fallback, Arctic) | **GEBCO_2026 Grid** | 15 arc-second (~450 m) | Global ocean and land | download.gebco.net (user-defined area: netCDF, GeoTIFF, Esri ASCII) | Public domain, free of charge; acknowledge GEBCO | **Used** for the Atlantic (CEDA tiles, `remote_tiles` adapter, 2 km grid). Not used for the world or the Barents Sea (IBCAO covers the Arctic) |
| Sea floor (Arctic) | **IBCAO v5.2** (400 m) | 400 m | Arctic Ocean incl. east Barents, north of Svalbard | CEDA zip (776 MB), streamed, clipped and deleted | Open; terms on the GEBCO page, not for navigation | **Used** for the Barents Sea east of 43 E and the far north |
| Land (UK) | **OS Terrain 50** | 50 m | Great Britain incl. Shetland | OS Downloads API, no key | OS OpenData (OGL) | **Used** (North Sea, NE Europe) |
| Land (Svalbard) | **NPI Svalbard DTM 20** | 20 m | Svalbard | Geonorge download | CC BY 4.0 | **Used** (Barents Sea) |
| Sea floor (Norway, higher detail) | **Kartverket dybdedata: terrain models 50 m grid** | 50 m | Norwegian waters | Geonorge download | CC BY 4.0 for the 50 m model; 5 m and 25 m grids inside 12 nm are classified; raw data on application | **Used** (see the 50 m row below; the 25 m model outside 12 nm is also used) |
| Land (primary) | **Copernicus DEM GLO-90** (GLO-30 where released) | 90 m (30 m) | Global | Open AWS buckets `copernicus-dem-90m`, `copernicus-dem-30m` (1° Cloud Optimized GeoTIFFs) | Copernicus licence, free; attribution "© DLR e.V. 2010–2014 and © Airbus 2014–2018, provided under COPERNICUS by the European Union and ESA". Heights on EGM2008 | **Used**: GLO-30 first, GLO-90 where a 30 m tile is withheld |
| Sea floor (Norway) | **Kartverket sea-floor terrain model 50 m** (`dybdedata terrengmodeller 50 m`) | 50 m | Norwegian waters (half-degree cells NHS-Drrcc) | Geonorge download API, `scripts/fetch_kartverket_sea.py` | CC BY 4.0 "© Kartverket"; 5 m / 25 m inside 12 nm classified | **Used** (demo page) |
| Sea floor (Denmark) | **Denmark's Depth Model 50 m** (2024) | 50 m | Danish EEZ | Dataforsyningen GeoTIFF or web service | Free marine data; credit "Danmarks Dybdemodel, 50 m opløsning" with retrieval date; not for navigation | Candidate |
| Sea floor (UK) | **UKHO ADMIRALTY Marine Data Portal** survey surfaces | survey-dependent | UK waters (footprints) | portal download | Open Government Licence v3 + no-navigation term | Candidate (EMODnet composites many) |
| Land (Denmark) | **Danmarks Højdemodel (DHM) terrain** | 0.4 m (lidar) | Denmark | Dataforsyningen (free account) | Free; check current terms | Candidate |
| Land (UK) | **OS Terrain 50** | 50 m | Great Britain | OS Data Hub | OS OpenData | Candidate |
| Glaciers | **RGI 6.0** via GLIMS WFS (`GLIMS:RGI_Scandinavia`) | outlines (NVE source, ~1999–2006) | Scandinavia | `scripts/fetch_glaciers.py` | CC BY 4.0 | **Used** (white layer); NVE 2018–19 inventory is the newer upgrade |
| Land (Norway, detail) | **Kartverket DTM 10** | 10 m | Norway | Geonorge download (UTM 32/33/35) | CC BY 4.0, "© Kartverket" | Candidate for large scales |
| Coastline, lakes (Norway) | **Kartverket N50 / N250 / N1000 kartdata** | 1:50k – 1:1M | Norway | Geonorge download | CC BY 4.0, "© Kartverket" | Planned: authoritative coastline and lakes per scale |
| Coastline (small scales, global) | **Natural Earth 10m** | 1:10M | Global | naturalearthdata.com | Public domain | Planned: overview fallback |

Notes
- EMODnet's grid includes land heights near the coast; Relief uses Copernicus for land where it shows land
  (above 0.5 m) and EMODnet depth elsewhere.
- Vertical datums differ (Copernicus: EGM2008 geoid; EMODnet: Lowest Astronomical Tide where available). At
  contour intervals of 50 m and more the difference does not show; it matters for anything near 0 m.

- Permanent snow: no Norwegian, Danish or UK agency publishes a permanent snow line. Glacier outlines are the
  observed "always white" layer; any modelled snow line must be labelled Interpreted.

Higher-resolution candidates per region (GLO-30, ArcticDEM, NPI Svalbard, Kartverket seamless terrain and 25 m sea floor, IBCAO v5, GEBCO_2026, OS Terrain 50 and others), with access method, licence and how far each was checked: [hires-sources.md](hires-sources.md) and `regions/sources.json`.
