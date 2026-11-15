# Slide map: one country cut out of the terrain

Written 2026-11-15. A map for slides and summary displays rather than for data: mainland Norway alone, the sky shade
(docs/sky-view.md) on a very subdued, nearly transparent fill, the country's outline, and its major cities. Everything
outside the country is transparent, so the picture sits on any slide background.

```
uv run python scripts/slide_map.py norway              # 1 px per 1,000 m cell: about 1,300 x 1,600 px
uv run python scripts/slide_map.py norway --scale 2    # 2 px per cell for a sharper slide
```

Writes to `data/out/norway/` (a release folder, not committed):

| File | Content |
|---|---|
| `slide_norway_light.png`, `slide_norway_dark.png` | RGBA; the two differ only in the ink of the outline, dots and labels (dark ink for light slides, light ink for dark slides) |
| `slide_norway.svg` | the outline, dots and labels as editable vectors over the light PNG, in the same pixel frame |
| `slide_norway.json` | frame, cropped extent, cell, pixel positions of the cities, terrain source, attribution |

## The design

- **Shade as ink, not colour.** The sky shade is drawn as two inks on a transparent sheet: dark where the shade falls
  below flat ground (the hollows, up to 62 % opacity), white where it rises above it (the lit slopes, up to 45 %). The
  fill under them is one pale tint at 32 % (22 % in the dark variant). On a white slide the result is a faint grey-green
  country with its relief; on a dark slide the same file shows the lit slopes and keeps the hollows.
- **Outline.** The coast is traced from the terrain's own 0 m line, so the fjords are the terrain's; the land border
  with Sweden, Finland and Russia is Natural Earth's 10 m admin-0 line, buffered three cells so its generalised line
  does not clip the terrain. Svalbard, Jan Mayen and Bouvet are left out (mainland and its islands only).
- **Cities.** Oslo, Bergen, Trondheim, Stavanger and Harstad from Natural Earth's populated places, a dot with a white
  ring and a label in Segoe UI (the house sans, Instrument Sans, is not installed as a font file; the SVG names both).
  The label sits to the right of the dot, or to the left on the west coast so it stays on the land.
- **Frame.** The `norway` region in `regions/regions.json` (ETRS89 / UTM 33N, the national projection) is the lon/lat
  box's outer rectangle; the picture is cropped to the country plus a margin of 28 cells, so the file is Norway alone.

## Terrain

The region is registered but not built from its own sources. Until then the slide map warps the Europe frame's merged
grid (`data/raw/europe_s2s/hires.tif`, 1,600 m) into the frame at 1,000 m: coarse, and honest at slide scale, where
one pixel is about a kilometre. `build_hires.py norway` with the plan in `regions/sources.json` (GLO-30 land,
Kartverket 50 m and EMODnet sea, 500 m web cell) would sharpen the fjord coast; the script takes the region's own
`hires.tif` as soon as it exists.

## Attribution

The JSON carries the lines to show beside the picture: the terrain sources of the grid used (Copernicus, EMODnet,
ETOPO for the Europe grid) and "Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com".
`scripts/fetch_natural_earth.py` records the fetch in `data/raw/natural_earth/provenance.json`.
