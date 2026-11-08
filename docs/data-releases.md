# Data releases

The repository holds **code, configuration and small files**. The built layers (tile pyramids, elevation textures, vector
layers: about 190 MB for five regions) are **GitHub Release assets**, because they are already compressed, are re-made
whenever sources improve, and would otherwise add a full copy to git history on every rebuild.

| Where | What |
|---|---|
| git | scripts, `regions/*.json`, docs, tests, the small Vestland proof of concept in `data/out/vestland/` |
| release `data-YYYY-MM-DD` | `relief-data-<region>.tar.gz` per region, plus `manifest.json` (sha256, sizes, sources, attribution) |
| `data/raw/` (local, ignored) | downloaded source data and merged high-resolution grids |

## Use the data

```
uv run python scripts/fetch_data.py                  # latest data release -> data/out/ (checks sha256)
uv run python scripts/fetch_data.py north_sea world  # just these regions
```

The Pages workflow does the same before it runs the tests and assembles the site, so a deploy always serves a published,
checksummed release. A repository that is public needs no token.

## Publish new data

After a rebuild (`build_hires.py`, `render_region.py`, `build_tiles.py`):

```
uv run python scripts/publish_data.py build                     # data/out/<region>/ -> dist/ (tarballs + manifest.json)
uv run python scripts/publish_data.py release --dry-run         # shows the gh command
uv run python scripts/publish_data.py release --tag data-2026-11-08
```

`release` needs the `gh` CLI, logged in. Re-run the Pages workflow afterwards (push, or Actions > Run workflow) to pick up
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
