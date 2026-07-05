# A* shortest path

`pyvisgraph` searches the visibility graph with **A\*** by default
(`VisGraph.shortest_path(origin, destination)`). The heuristic is the
straight-line Euclidean distance to the destination, which is admissible and
consistent on a planar visibility graph with Euclidean edge weights, so A*
returns the same optimal path as Dijkstra while settling far fewer nodes.

The original Dijkstra search is still available:

```python
g.shortest_path(origin, destination, algorithm='dijkstra')
```

Both algorithms live in `pyvisgraph/shortest_path.py` (`astar` and
`dijkstra`); the module-level `shortest_path()` dispatches on the
`algorithm` argument and defaults to `'astar'`.

## Profiling: A* vs Dijkstra

Benchmarked with `examples/profile_shortest_path.py` on the 10 generated
benchmark maps in `examples/kml/benchmark/` (created by
`examples/generate_benchmark_kml.py`; jittered convex obstacles of increasing
count in a 0.5° x 0.5° extent). Per map: 20 seeded-random
origin/destination pairs in free space, best-of-3 timing per query, and both
algorithms verified to return paths of identical length on every query.

Environment: Python 3.12.3, Linux x86_64, 14 CPU cores (cores only affect the
one-time graph build; queries are single-threaded). Run on 2026-07-05.

| map        | polygons | vertices | visgraph edges | Dijkstra (ms/query) | A* (ms/query) | speedup | Dijkstra settled nodes | A* settled nodes |
|------------|---------:|---------:|---------------:|--------------------:|--------------:|--------:|-----------------------:|------------------:|
| map_01.kml |        3 |       16 |             50 |               1.025 |         0.883 |   1.16x |                    6.2 |               2.2 |
| map_02.kml |        6 |       34 |            192 |               2.227 |         1.773 |   1.26x |                   13.7 |               2.1 |
| map_03.kml |       12 |       84 |            835 |               3.347 |         2.267 |   1.48x |                   38.1 |               3.5 |
| map_04.kml |       20 |      111 |          1,635 |               5.304 |         3.317 |   1.60x |                   45.0 |               2.9 |
| map_05.kml |       30 |      180 |          3,541 |              14.104 |         8.329 |   1.69x |                   67.0 |               3.1 |
| map_06.kml |       45 |      254 |          5,870 |              12.450 |         6.724 |   1.85x |                  115.5 |               4.5 |
| map_07.kml |       60 |      351 |          9,438 |              22.681 |        12.118 |   1.87x |                  159.2 |               5.6 |
| map_08.kml |       80 |      472 |         15,349 |              29.704 |        15.028 |   1.98x |                  190.4 |               5.8 |
| map_09.kml |      105 |      643 |         20,452 |              48.822 |        22.043 |   2.21x |                  333.9 |              10.1 |
| map_10.kml |      130 |      770 |         26,560 |              66.907 |        31.445 |   2.13x |                  354.7 |              11.5 |

Settled nodes = entries in the algorithm's distance map when the destination
is reached (the algorithmic work of the search itself).

### Observations

- **A* settles 3x-35x fewer nodes than Dijkstra**, and the gap widens with map
  complexity (6.2 vs 2.2 nodes on the smallest map, 354.7 vs 11.5 on the
  largest). The Euclidean heuristic steers the search almost straight at the
  destination.
- **End-to-end query speedup is a more modest 1.2x-2.2x** because a query for
  points not already in the visibility graph is dominated by computing the
  temporary visibility edges for the origin and destination
  (`visible_vertices`, O(n log n) per point), which is identical for both
  algorithms. The search itself is where the ~30x node reduction shows up.
- Both algorithms returned **identical path lengths on all 200 queries**, as
  expected from an admissible, consistent heuristic. On symmetric maps two
  optimal paths can tie, in which case the algorithms may return different
  (equally short) vertex sequences.

### Reproducing

```bash
poetry install --extras viewer          # geopandas needed to load KML
poetry run python examples/generate_benchmark_kml.py
poetry run python examples/profile_shortest_path.py
```
