# Performance: Relief and the repos that draw on it

Reviewed 2026-11-11. What a page fetches from Relief, what it costs, what was changed, and what is left. Sizes are
for the NE Europe frame unless said otherwise; "transfer" is bytes over the wire before the server's gzip, which helps
JSON (about four to one) and not images.

## What each consumer fetched, and fetches now

| Consumer | Before | Now |
|---|---|---|
| geology-map-processing preview, Bedrock geology page | `regional_hillshade.png` 460 KB, `regional.geojson` 474 KB, both base PNGs 1,066 KB, manifest; a pixel pass to remap the hillshade on every load | `regional_base_<scheme>.webp` 68 KB, `regional_shade.webp` 130 KB, manifest; no bands, no remap |
| source-to-sink preview, Bedrock s2s page | hillshade 460 KB, bands 474 KB, one base PNG 576 KB, slope flow 13.8 MB GeoJSON; remap pass | base 68 KB, shade 130 KB, slope flow 7.5 MB compact (released separately from Pages), loaded after the first paint |
| Sand-from-the-Source story | hillshade and both base PNGs reduced to the page width, per frame | unchanged (that repo is mid-rework); the WebP tints and shade are the drop-in, about 300 KB a frame instead of 1.4 MB |
| Bedrock `site/relief/<frame>/` | 6.5 MB for three frames (PNGs, bands, overview copies) | about 1.4 MB: WebP tints, shade, bands as the fallback, manifest |
| Wildcat | the North Sea bands converted to lon/lat at build time (`build_relief_base.py`) | unchanged; a build-time conversion, not a page cost |
| Sheet | `print_layers.py` products on disk | unchanged; not a page |

Relief-side cost per frame: 2.0 MB of page assets became 0.2 MB, and the consumer's canvas work dropped by one
full-image `getImageData` pass. The viewers' own redraw work was cut separately (Path2D batches; Bedrock commit
`5141691` and the previews' commits of 2026-11-11): Norway regional 3.2 s to 0.7 s per redraw in headless Chrome.

## Relief's own pages

- The gallery loads one card-sized texture per region (`elev_card.webp`, since 2026-11-10) and draws lazily; the explore
  page loads tiles on demand. Both are already frugal.
- **The Pages deployment copies all of `data/out` into `_site/data` (331 MB today).** Most of it is never fetched by a
  page: the full `demo/elev.webp` textures (4 to 9 MB a region, used only by the techniques page for Vestland), the
  `compare/` sets, `detail.geojson` and the bands (no page fetches them), the base PNGs now that the WebP exists. The
  tiles (5 to 20 MB a region) are the only large thing a page needs. An allow-list copy (tiles, `tiles.json`, manifest,
  `elev_card.webp`, `zones.png`, the WebP tints and shade, the regions files, and Vestland's demo set) would put the site
  near 150 MB, and dropping `atlantic` and `world` detail levels from Pages (release only) near 100 MB. Pages deploys
  have timed out near 100 MB elsewhere (Bedrock, three times on 2026-11-10), so this is the next thing to do here; it is
  a change to `.github/workflows/pages.yml` and a small `scripts/site_data.py`, not to any product.

## What is left, in order

1. **Pages allow-list** (above). Half a day, cuts the deploy by two thirds.
2. **Tiles as the texture source for consumers.** A consumer that needs the terrain at more than the regional cell
   (Sheet at 1:1.5M, the story's zoomed frames) reads the tile pyramid; the base tint could be rendered per tile level
   by `base_tint.py` so a page can zoom without a new product. Only worth it when a consumer asks.
3. **Bands as TopoJSON.** `regional.geojson` is 474 KB because every band repeats the coast; a quantised TopoJSON with
   shared arcs would be about a third. Low priority now that pages fetch the bands only as a fallback.
4. **Neutral hillshade at source.** `build.py` still writes the light-toned PNG for the print path and Sheet; moving the
   PNG itself to mid grey is a contract change for Sheet's multiply blend and is deferred (`plan-europe-frame.md`).
