# Open sources

Checked 2026-11-07. Keep the attribution lines with any map made from these data.

| Use | Dataset | Resolution | Coverage | Access | Licence / terms | Status here |
|---|---|---|---|---|---|---|
| Sea floor (primary, Europe) | **EMODnet Digital Bathymetry DTM 2024** | 1/16 arc-minute (~115 m) | European seas incl. North Sea, Norwegian Sea, Barents Sea | WCS `ows.emodnet-bathymetry.eu/wcs` (coverage `emodnet__mean`), or 59 tiles (GeoTIFF, NetCDF, ASCII) | Open access; attribution "EMODnet Bathymetry Consortium (2024): EMODnet Digital Bathymetry (DTM)". Check each tile's metadata licence: some contributing surveys are not open data in raw form | **Used** (WCS box cut) |
| Sea floor (global fallback, Arctic) | **GEBCO_2026 Grid** | 15 arc-second (~450 m) | Global ocean and land | download.gebco.net (user-defined area: netCDF, GeoTIFF, Esri ASCII) | Public domain, free of charge; acknowledge GEBCO | Planned (outside EMODnet, e.g. north of Svalbard) |
| Sea floor (Norway, higher detail) | **Kartverket dybdedata: terrain models 50 m grid** | 50 m | Norwegian waters | Geonorge download | CC BY 4.0 for the 50 m model; 5 m and 25 m grids inside 12 nm are classified; raw data on application | Candidate for coastal detail |
| Land (primary) | **Copernicus DEM GLO-90** (GLO-30 where released) | 90 m (30 m) | Global | Open AWS buckets `copernicus-dem-90m`, `copernicus-dem-30m` (1° Cloud Optimized GeoTIFFs) | Copernicus licence, free; attribution "© DLR e.V. 2010–2014 and © Airbus 2014–2018, provided under COPERNICUS by the European Union and ESA". Heights on EGM2008 | **Used** (GLO-90) |
| Land (Norway, detail) | **Kartverket DTM 10** | 10 m | Norway | Geonorge download (UTM 32/33/35) | CC BY 4.0, "© Kartverket" | Candidate for large scales |
| Coastline, lakes (Norway) | **Kartverket N50 / N250 / N1000 kartdata** | 1:50k – 1:1M | Norway | Geonorge download | CC BY 4.0, "© Kartverket" | Planned: authoritative coastline and lakes per scale |
| Coastline (small scales, global) | **Natural Earth 10m** | 1:10M | Global | naturalearthdata.com | Public domain | Planned: overview fallback |

Notes
- EMODnet's grid includes land heights near the coast; Relief uses Copernicus for land where it shows land
  (above 0.5 m) and EMODnet depth elsewhere.
- Vertical datums differ (Copernicus: EGM2008 geoid; EMODnet: Lowest Astronomical Tide where available). At
  contour intervals of 50 m and more the difference does not show; it matters for anything near 0 m.
