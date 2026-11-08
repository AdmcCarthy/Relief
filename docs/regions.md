# Regions

Named map frames, defined once in [`regions/regions.json`](../regions/regions.json) and shared by Relief's own
pipeline and by any other app (SubScout figures, MapLibre or d3 maps, notebooks). A region is a projected
rectangle: a CRS, an extent in metres, a lon/lat box that contains it, and the levels of detail (cell sizes) its
layers are built at.

| id | What it frames | CRS | Frame |
|---|---|---|---|
| `vestland` | Bergen coast, proof of concept | ETRS89 / UTM 32N (EPSG:25832) | 206 × 266 km |
| `north_sea` | Norwegian North Sea (all Sodir North Sea blocks and fields) with UK, Danish, German, Dutch margins | EPSG:25832 | 740 × 880 km |
| `norwegian_sea` | Sodir Norwegian Sea blocks and fields, Nordland coast | Lambert conformal conic, 8 E (custom) | 1,070 × 1,000 km |
| `barents_sea` | Barents Sea, northern Norway, Kola, Svalbard, Novaya Zemlya; **Norway at the bottom** | north-polar Lambert azimuthal equal-area, 30 E down (custom) | 2,150 × 1,800 km |
| `ne_europe` | UK, Norwegian North Sea, Denmark, Netherlands, Germany, Poland; **not** the Norwegian Sea | ETRS89 / LAEA Europe (EPSG:3035) | 2,270 × 1,580 km |
| `atlantic` | The Atlantic, Arctic to Southern Ocean, for spreading ridges; ocean depth scale | Lambert azimuthal equal-area, 25 W (custom) | 11,790 × 15,080 km |
| `world` | Locator and global context; ocean depth scale | Equal Earth (EPSG:8857) | 34,488 × 16,786 km |

## Using a region elsewhere

Published with the preview at `https://admccarthy.github.io/Relief/regions/`:
`regions.json` (everything below), `regions.geojson` (outlines in lon/lat, curved edges densified, for locator
maps) and `coverage.json` (the checks).

Each region has: `id`, `name`, `description`, `crs.proj4` / `crs.epsg` / `crs.code`, `extent` `[x0, y0, x1, y1]`
in projected metres, `bbox` `[w, s, e, n]` in degrees, `size_km`, `lods` (cell size per level), `bathymetry` (`shelf` or `ocean`: which sea colour scale, see [depth-scale.md](depth-scale.md)),
`levels` (optional vector depth and height classes), `built` (layers exist under `data/<id>/` on the preview).

```js
// d3 / proj4js: put your own data into the region's frame
const r = (await (await fetch(".../regions/regions.json")).json()).regions.find((r) => r.id === "barents_sea");
const to = proj4("EPSG:4326", r.crs.proj4);                 // proj4js: lon/lat -> region metres
const [x0, y0, x1, y1] = r.extent;
const proj = d3.geoIdentity().reflectY(true).fitSize([W, H], { type: "MultiPoint", coordinates: [[x0, y0], [x1, y1]] });
const xy = (lon, lat) => proj(to.forward([lon, lat]));       // and draw Relief's layers with the identity projection
```

```python
import json, urllib.request
from pyproj import Transformer
r = next(r for r in json.load(urllib.request.urlopen(".../regions/regions.json"))["regions"] if r["id"] == "ne_europe")
to_region = Transformer.from_crs("EPSG:4326", r["crs"]["proj4"], always_xy=True)
```

Relief's layers (`data/<id>/<lod>.geojson`, `<lod>_hillshade.png`, `manifest.json`) are already in the region's
projected metres, so draw them with an identity transform and put your data into the same frame (as above).
Inside this repo `scripts/areas.py` exposes the same registry as `AREAS`.

## Adding or changing a region

1. Edit `regions/regions.json`: `crs`, `design` (a `lonlat_box` or a list of `points`, plus `fit`: `outer` covers the
   box, `inner` stays inside it; `north_at: [lat, lon]` pins the north edge to a parallel at one longitude), `fetch`
   (`step_deg`, sources) and `lods` (cell sizes in metres).
2. `uv run python scripts/regions.py sync` derives `extent`, `bbox`, `size_km`, `proj4`, `built` and `regions.geojson`.
3. `uv run python scripts/fetch_region.py <id> && uv run python scripts/build.py <id>`, then `sync` again (sets `built`).
4. Regions with a `coverage` block are checked by `uv run python scripts/fetch_sodir.py && uv run python scripts/regions.py check`
   and by the tests (`tests/test_regions.py`).

## How the frames were chosen, and what was checked

- **Norwegian regions (North Sea, Norwegian Sea, Barents Sea):** every Sodir block (1,827, layer 802 of the Sodir
  FactMaps service) and field (142, layer 502) is assigned to its Sodir main area. Each region contains 100 % of its
  own area's blocks and fields (`regions/coverage.json`). The North Sea / Norwegian Sea boundary is exactly 62 N.
- **NE Europe:** contains all 284 Norwegian North Sea blocks (99.7 % by area) and all 107 fields, and none of the 31
  Norwegian Sea fields (0.2 % of Norwegian Sea block area leaks in at the north edge: a rectangle cannot follow a
  parallel, so the edge is pinned to 62 N at 3 E). Offshore evidence from 16,000 EMODnet Human Activities wells: UK,
  Netherlands, Denmark, Germany and Poland are 99.7–100 % inside (22 UK wells far to the west, in the Celtic Sea and
  at 9.8 W, are outside). **Onshore** Germany (Molasse, Weser-Ems, Schleswig-Holstein) and Poland (Polish Lowland,
  Carpathian foredeep, to 24.5 E) are framed from basin knowledge, not data: no open onshore field outlines were checked.
- **Barents Sea, polar view:** the 30 E meridian is vertical, so Finnmark (25 to 31 E) sits at the bottom, Svalbard top
  left, Novaya Zemlya right. Projection: `+proj=laea +lat_0=90 +lon_0=30` (equal-area, so areas compare fairly).
  EMODnet stops at 43 E: east of it the sea floor comes from ETOPO 2022 (about 1.8 km), so seams are visible at fine
  levels of detail.
- **World:** Equal Earth is not a rectangle, so the layers' sea fills the whole frame; clip to the Equal Earth outline
  (d3 `geoEqualEarth` sphere, or the globe path) when drawing. The land and sea layers come from ETOPO 2022 sampled
  every fifth cell (the server is too slow for more), so treat the world as a locator, not a coastline reference.
- **Resolution:** large regions are fetched at 0.4 to 0.9 km grid steps (EMODnet averaged down from 115 m), so the finest
  level of detail is 500 m to 2 km. Use `vestland`-style full-resolution fetches for small areas.
