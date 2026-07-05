# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package management

This package is managed by **Python Poetry** (`pyproject.toml` + `poetry.lock`). Do not use pip/setup.py directly; run everything through `poetry run` or a `poetry shell`.

```bash
poetry install --extras viewer   # dev install incl. optional GUI deps (geopandas, PyQt6)
poetry install                   # core library only (tqdm is the sole runtime dep)
poetry lock                      # after changing dependencies in pyproject.toml
```

## Commands

```bash
poetry run pytest tests/test_pvg.py tests/test_viewer_loader.py   # the reliable test suite
poetry run pytest tests/test_pvg.py -k test_angle                 # single test by keyword
poetry run pyvisgraph-viewer examples/kml/simple.kml              # launch the GUI viewer
tox                                                                # test across py310-py314
```

Caveat: `tests/test_deploy.py` requires GSHHS shapefiles and a prebuilt `world.pk1` that are **not** in the repo (must be downloaded separately); it fails without them. `tests/test_viewer_loader.py` auto-skips when the `viewer` extras are not installed.

## Architecture

Core library (`pyvisgraph/`) is a planar visibility-graph builder + Dijkstra shortest path:

- `graph.py` — primitives: `Point` (x, y, polygon_id; equality on x/y only), `Edge` (order-independent), `Graph` (maps Point → incident Edges; constructor takes a list of polygons, where each polygon is a list of in-order `Point`s — a single polygon must still be nested: `[[p1, p2, p3]]`. Rings are auto-closed and a duplicated closing point is popped).
- `visible_vertices.py` — the O(n² log n) rotational-sweep visibility algorithm (D.T. Lee) plus geometry helpers (`point_in_polygon`, `closest_point`, `edge_distance`). Orientation uses the `CW`/`CCW`/`COLLINEAR` constants; collinearity is sensitive to `COLIN_TOLERANCE` (rounding) — historically the source of subtle bugs (see commit history).
- `shortest_path.py` — Dijkstra over the visibility graph; extra origin/destination edges can be passed in without mutating the graph.
- `vis_graph.py` — the `VisGraph` facade users interact with: `build(polys, workers, status)` (multiprocessing when `workers > 1`; `status` only toggles a tqdm bar — there is no progress callback), `shortest_path`, `update`, pickle-based `save`/`load`.

All math is **Euclidean/planar**; geographic data uses the convention x=longitude, y=latitude, and real-world distances are computed outside the library (see `examples/2_calculate_shortest_distance.py`, which uses haversine).

### GUI viewer (`pyvisgraph/viewer/`)

Optional PyQt6 + geopandas viewer, exposed as the `pyvisgraph-viewer` script (entry point in `[tool.poetry.scripts]`). Hard rules:

- geopandas/PyQt6 are **optional extras** (`viewer`). Never import them at module level anywhere that gets pulled in by `import pyvisgraph` — `cli.py` guards its imports and prints an install hint when they are missing.
- CI (`.github/workflows/ci.yml`) tests Python 3.10-3.14 with Poetry 1.8.2; the viewer extras are only installed on 3.12.
- `loader.py` must stay Qt-free so loader tests run headless. It converts any geopandas-readable file into pyvisgraph polygons: MultiPolygons are exploded, interior rings (holes) become separate obstacle polygons, non-polygon geometries are skipped.
- `worker.py` runs the blocking `VisGraph.build()` on a QThread; `scene.py`/`view.py` render with a y-flipped view (map north = screen up) and cosmetic pens (constant pixel width under zoom). Visibility edges are batched into a single `QGraphicsPathItem` for performance.
- GUI behavior can be smoke-tested headless with `QT_QPA_PLATFORM=offscreen`.

Example obstacle maps for the viewer live in `examples/kml/` (simple/medium/complex).

## Conventions (from CONTRIBUTING.md)

- Commit messages: imperative mood, subject ≤ 50 chars, blank line before body; body explains what/why.
- Branch names: `<type>/<name>` with type `ft` (feature) or `bug` (bugfix), e.g. `ft/progressbar`.
