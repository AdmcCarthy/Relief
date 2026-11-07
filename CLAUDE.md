# Relief: working rules

Open topography and bathymetry for data maps, reusable by any story (SubScout) or map. Owner: Adam McCarthy.

- Open sources only; record licence and attribution in docs/sources.md and on every output.
- Generalise by intended map scale (LOD config in scripts/build.py): cell size, smoothing, min feature area and
  gap closing in cells. Stacked ("layer cake") contours; pre-projected metres rounded to 10 m.
- Disk is small (10 GB): fetch only area boxes (WCS / single tiles), never whole datasets; data/raw is ignored.
- Tests (tests/) check nesting, generalisation and size/draw budgets. British English, metric.
