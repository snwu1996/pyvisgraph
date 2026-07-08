# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## This branch: cvisgraph C backend (`snwu/cvisgraph`)

This branch replaces the pure-Python algorithm internals with **cvisgraph**, a C library implementing the same algorithms 1:1 (identical results, ~40x faster single-threaded, ~100x with 4 worker threads). The public API is unchanged. Key differences from `main`:

- The geometry/sweep/shortest-path code paths call `libcvisgraph.so` through `pyvisgraph/_clib.py` (stdlib ctypes). `Point`/`Edge`/`Graph` remain pure Python; `Graph._to_c()` caches the C-side conversion.
- `build(workers=N)` uses pthreads inside the C library instead of multiprocessing.
- `save()`/`load()` use a new snapshot pickle format; `.pk1` files from `main` cannot be loaded.
- **Build step required**: `make cbackend` compiles the C library and copies `libcvisgraph.so` into the package. `CVISGRAPH_DIR` points at the local sibling checkout `../cvisgraph` for now (eventually a cvisgraph release from GitHub). `_clib.py` also honors `CVISGRAPH_LIB`/`CVISGRAPH_DIR` env vars at import time.

```bash
make cbackend    # build the C backend (requires ../cvisgraph checkout)
make test        # cbackend + the reliable pytest suite
```

## Package management

This package is managed by **Python Poetry** (`pyproject.toml` + `poetry.lock`). Do not use pip/setup.py directly; run everything through `poetry run` or a `poetry shell`.

```bash
poetry install                   # core library only (tqdm is the sole runtime dep)
poetry lock                      # after changing dependencies in pyproject.toml
```

## Commands

```bash
poetry run pytest tests/test_pvg.py tests/test_boundary_scenarios.py   # the reliable test suite
poetry run pytest tests/test_pvg.py -k test_angle                      # single test by keyword
tox                                                                     # test across py310-py314
```

Caveat: `tests/test_deploy.py` requires GSHHS shapefiles and a prebuilt `world.pk1` that are **not** in the repo (must be downloaded separately); it fails without them.

The interactive GUI viewer that used to live here (`pyvisgraph/viewer/`, the `pyvisgraph-viewer` script) has moved to the separate **`vgstudio`** project (`../visgraph-studio`), which depends on this library via a local path. All geopandas/PyQt6/shapely dependencies and the example/benchmark KML maps moved with it.

## Architecture

Core library (`pyvisgraph/`) is a planar visibility-graph builder + Dijkstra shortest path:

- `graph.py` — primitives: `Point` (x, y, polygon_id; equality on x/y only), `Edge` (order-independent), `Graph` (maps Point → incident Edges; constructor takes a list of polygons, where each polygon is a list of in-order `Point`s — a single polygon must still be nested: `[[p1, p2, p3]]`. Rings are auto-closed and a duplicated closing point is popped).
- `visible_vertices.py` — the O(n² log n) rotational-sweep visibility algorithm (D.T. Lee) plus geometry helpers (`point_in_polygon`, `point_in_solid`, `closest_point`, `edge_distance`). Solidness follows the **even-odd rule** across all polygons (`point_in_solid`/`edge_in_polygon`): the hole ring of a donut-shaped obstacle (loaded as a nested polygon) is free space, points there can reach each other but not the outside. Orientation uses the `CW`/`CCW`/`COLLINEAR` constants; collinearity is sensitive to `COLIN_TOLERANCE` (rounding) — historically the source of subtle bugs (see commit history).
- `shortest_path.py` — Dijkstra over the visibility graph; extra origin/destination edges can be passed in without mutating the graph.
- `vis_graph.py` — the `VisGraph` facade users interact with: `build(polys, boundary, workers, status, progress)` (multiprocessing when `workers > 1`; `status` toggles a tqdm bar, `progress` is an optional `progress(done, total)` callback reporting vertices completed), `shortest_path`, `update`, pickle-based `save`/`load`. Passing `boundary` (a navigable-region ring list, same nested format as `polys`) inverts the map: everything outside the boundary becomes solid off-limits space, the interior is free, and `polys` are obstacle islands inside it. The frame construction + even-odd inversion live here (`invert_boundary`/`boundary_frame`, `FRAME_MARGIN_FRAC`) — shapely-free, so this is where the boundary-zone logic belongs; `vgstudio`'s KML loader only cleans geometry with shapely (union/repair/straddler resolution) and delegates the inversion here.

All math is **Euclidean/planar**; geographic data uses the convention x=longitude, y=latitude, and real-world distances are computed outside the library (see `examples/2_calculate_shortest_distance.py`, which uses haversine).

### Tests

- `tests/test_pvg.py` — the core geometry/graph/shortest-path unit tests.
- `tests/test_boundary_scenarios.py` — even-odd donut, exclusion-zone boundary inversion, and concave-detour behaviors built from **in-memory polygons** (no geopandas/KML). This replaces the coverage the old viewer loader test gave, keeping the suite self-contained; the KML-driven loader tests now live in the `vgstudio` project.

## Conventions (from CONTRIBUTING.md)

- Commit messages: imperative mood, subject ≤ 50 chars, blank line before body; body explains what/why.
- Branch names: `<type>/<name>` with type `ft` (feature) or `bug` (bugfix), e.g. `ft/progressbar`.
