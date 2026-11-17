# Request: a Central North Sea frame and a fine sea floor for field maps

**Status 17 November 2026.** Built on the owner's request on 16 November, merged and released on the 17th: the layers
are in the data release `data-2026-11-17` and the merged grid in `grids-2026-11-17`. Both releases carry the other regions'
archives unchanged from `data-2026-11-15-linear` and `grids-2026-11-15`. `central_graben` is registered with its extent exactly as asked, fetched with `build_hires.py` (GLO-90 and
EMODnet 2024 only), merged at 125 m (8,400 x 3,600) and built: three levels of detail, a six-level tile pyramid down to
125 m (188 tiles), base tints, sky shade, and a fine base of 5,360 x 3,600 pixels at 125 m over the field-map area from the
new `scripts/fine_base.py`. 92 MB in `data/out/central_graben`, 303 MB of fetched pieces and a 79 MB merged grid in `data/raw`.

Written the same day as a plan, before anything was fetched. A private Central North Sea study draws every map in a fixed,
named view: one area frame, sector frames at one scale, and a 30 x 30 km window for each of 288 fields and discoveries. It
takes terrain through Relief and never colours, shades or resamples it. No existing frame serves it: `north_sea` and
`north_sea_wide` are in UTM 32N, whose central meridian (9 E) turns the grid 6 to 7 degrees from north on the UK side, and
their detail level (300 m) gives a field window 100 pixels.

## What was asked

| Product | Frame (EPSG:25831, metres) | Cell | Use |
|---|---|---|---|
| Region `central_graben` | [-115000, 6060000, 935000, 6510000], 1,050 x 450 km | overview 2,000 m, regional 900 m, detail 300 m | area and sector maps, cut from the one frame |
| Fine base | [130000, 6060000, 800000, 6510000], 670 x 450 km | 125 m | the 288 field windows, cropped by the consumer |

The projection was settled beforehand: ETRS89 / UTM 31N, central meridian 3 E, through the middle of the graben. The extent
had to come out exactly as written, because the consumer's views are cuts of it on whole kilometres. Depth scale `shelf`.

## What was built, and how

1. **The region.** `design` takes a lon/lat box or points, never a projected rectangle, and a box's projected corners
   spread. The extent is pinned with two points 2.5 km inside the south-west and north-east corners, `margin_m: 0`,
   `round_m: 5000`: rounding outwards gives [-115000, 6060000, 935000, 6510000] exactly (bbox -7.528, 54.305, 10.486,
   58.74). It is a display frame of 2.33 : 1 and carries no `role`. Coverage: Ekofisk, Forties and Dan lie 89 to 207 km
   inside the edge (`regions.py check`, 3 of 3).
2. **The fetch.** 29 EMODnet chunks of 2 degrees at the native cell, none refused, 247 MB kept; 51 GLO-90 tiles holding
   land of 91 candidates, 56 MB kept. No ETOPO: EMODnet gives 99.3 % of the sea cells, and the rest (tidal flats,
   estuaries, 0.9 % of the frame) are set to -1 m by the merge.
3. **The standard layers.** `rebuild.py run central_graben`, then `sky_view.py`: the 300 m texture (3,500 x 1,500, 2.4 MB),
   tiles, `overview`, `regional` and `detail` vectors (0.06, 0.22, 1.17 MB) with hillshades, the regional tints and
   `regional_shade.webp`. `contract.py check` passes.
4. **The fine base.** Of the two routes, the region's own grid was taken, not a window: `scripts/window.py` writes squares
   named by a centre, and the 670 x 450 km area falls on whole cells of the 125 m grid (columns 1,960 to 7,320 of
   8,400). `scripts/fine_base.py central_graben --extent 130000 6060000 800000 6510000` writes `data/out/central_graben/fine/`:
   the tint in both themes by `base_tint.py`'s ramps, the sky shade (flat ground at 180, and a neutral copy at 128 with
   slopes stretched 2.5 times), the heights as a GeoTIFF, and a manifest with extent, cell, CRS, depth scale and ticks,
   shade model, sources and attribution (docs/base-maps.md).

## Findings

- **The 900 m level does not divide the frame.** 1,050 km is 1,166.67 cells, so `regional_hillshade.png` and
  `regional_shade.webp` are 1,166 pixels wide and stop 600 m short of the east edge, while the regional tint (1,167 pixels,
  resized) covers the whole extent. `build.py` has always cropped this way (`north_sea` is 822.2 cells wide); here it
  matters because views are cut by arithmetic. The 2,000 m and 300 m levels and the fine base divide exactly. A regional
  cell of 750 m (1,400 x 600) would remove the mismatch if the study draws the regional shade.
- **The fine shade is quiet over most of the area, and says so.** At the house exaggeration (2 x; Relief documents a
  stronger setting for ocean basins only, none for flat shelves) 79 % of shelf cells sit within one grey level of flat in
  the neutral shade and 96 % within four. A window at Ekofisk (61 to 77 m of water) spans grey 124 to 129 between its 1st
  and 99th percentiles; one at Dan, 127 to 128. Relief that does read: the Devil's Hole trenches (73 to 242 m in one
  window), tunnel valleys off eastern Scotland and in the outer Moray Firth, the sand ridges on the north flank of the
  Dogger Bank, and the edge of the Norwegian Channel (to 592 m in the fine area, 703 m in the frame).
- **The source grid's own marks show at 125 m.** Isolated pits one or two cells wide at Forties and the Witch Ground may be
  pockmarks or single soundings; the cell cannot separate them (interpreted). North-south rows of dots and faint seams
  near 5 to 5.5 E look like survey lines (interpreted from the picture, not checked against EMODnet's source index).
- **`regions.py sync` in a worktree without `data/out` turns every `built` flag off.** The other regions' flags were put
  back from the committed file. `central_graben` is `built: true` from the release of 17 November.

## Left to do

- The 900 m regional level (see the first finding) is unchanged.

## Sources and licence

Nothing new: EMODnet Bathymetry DTM 2024 and Copernicus DEM GLO-90, both in `docs/sources.md`, attribution lines unchanged
and written into the fine manifest. The land tint uses the Köppen-Geiger zones of Beck and others (2023), as every base tint does.
