# Data releases

The repository holds **code, configuration and small files**. The built layers (tile pyramids, elevation textures, vector
layers: about 190 MB for five regions) are **GitHub Release assets**, because they are already compressed, are re-made
whenever sources improve, and would otherwise add a full copy to git history on every rebuild.

| Where | What |
|---|---|
| git | scripts, `regions/*.json`, docs, tests, the small Vestland proof of concept in `data/out/vestland/` |
| release `data-YYYY-MM-DD` | `relief-data-<region>.tar.gz` per region, plus `manifest.json` (sha256, sizes, sources, attribution) |
| release `grids-YYYY-MM-DD` | `relief-grids-<region>.tar.gz`: the merged grids (`hires.tif` and its provenance) behind those layers, plus `manifest.json` |
| `data/raw/` (local, ignored) | downloaded source data, cached source pieces and the merged grids |

## Use the data

```
uv run python scripts/fetch_data.py                  # latest data release -> data/out/ (checks sha256)
uv run python scripts/fetch_data.py north_sea world  # just these regions
```

The Pages workflow does the same before it runs the tests and assembles the site, so a deploy always serves a published,
checksummed release. A repository that is public needs no token.

## Restore the merged grids on a new machine

Fetching and merging the sources is the slow stage (10 to 25 minutes a region, plus the source downloads). Its product, the
merged grid, is published as a second release series so a fresh checkout can skip it:

```
uv run python scripts/fetch_data.py --grids          # latest grids-* release -> data/raw/<region>/ (checks sha256)
uv run python scripts/fetch_data.py --grids atlantic # just one
```

A grid already built locally is kept unless `--force` is given. Then render and tile as usual (`render_region.py`,
`build_tiles.py`). What is not in the release: the cached source pieces in `data/raw/<region>/hires/`, so changing a source
list still means fetching that source again. The six grids are 551 MB packed (79 to 121 MB each): the GeoTIFFs are already
compressed, so the archive saves nothing. GitHub allows 2 GiB per release asset and does not cap the total; releases on a
public repository cost nothing and need no login to download.

## Rebuild in one command

From a merged grid to a region's published layers:

```
uv run python scripts/rebuild.py plan                       # which stages are stale, and why (no side effects)
uv run python scripts/rebuild.py run north_sea              # render, tiles, vectors, base: only the stale ones
uv run python scripts/rebuild.py run --download             # also restore missing grids from the latest grids-* release
uv run python scripts/rebuild.py run --force --package      # everything, then dist/ tarballs ready for publishing
```

A stage is stale when an output is missing or its input changed: the check compares a content hash with the one recorded
after the last successful run (`data/out/<region>/.rebuild-stamps.json`), so a re-merge that gives the same bytes does not
trigger a rebuild. `rebuild.py adopt <region>` records the stamps for outputs known to be current. The script never fetches
or merges source data: that stays with `build_hires.py`, which has to be asked for.

## Publish new data

After a rebuild (`build_hires.py`, `render_region.py`, `build_tiles.py`):

```
uv run python scripts/publish_data.py build                     # data/out/<region>/ -> dist/ (tarballs + manifest.json)
uv run python scripts/publish_data.py release --dry-run         # shows the gh command
uv run python scripts/publish_data.py release --tag data-2026-11-08
```

For the grids (after `build_hires.py`): `publish_data.py grids-build`, then `publish_data.py grids-release --tag grids-2026-11-10`.
`grids-build` refuses a grid built from a source marked `redistributable: false`, since a grid is a derived copy of its sources.

`release` and `grids-release` need the `gh` CLI, logged in. Re-run the Pages workflow afterwards (push, or Actions > Run workflow) to pick up
the new release.

## Licences

Every released region carries its attribution list in the manifest and in the release notes. Before a source is added to a
region plan, its licence has to be on record in `regions/sources.json`; sources that are not redistributable are marked
`redistributable: false` and a test refuses them in any plan. The Kartverket seamless terrain service is one: its Geonorge
record is under the Norge digitalt licence (partners only), so the Norwegian land in released tiles is Copernicus GLO-30,
not that lidar model.

## If it outgrows releases

Finer data (50 m or less) multiplies the size. The same tarballs can move to object storage with CORS (for example
Cloudflare R2) and the viewer can fetch tiles from there; nothing else changes.
