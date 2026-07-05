"""Profile A* vs Dijkstra shortest-path queries on the benchmark KML maps.

Loads examples/kml/benchmark/map_*.kml (run generate_benchmark_kml.py first),
builds the visibility graph once per map, then times shortest_path queries
with both algorithms over the same seeded-random origin/destination pairs.
Requires the viewer extras (geopandas) for KML loading:
poetry install --extras viewer.
"""
import glob
import os
import random
import time

from pyvisgraph.graph import Point, Graph, Edge
from pyvisgraph.shortest_path import astar, dijkstra
from pyvisgraph.vis_graph import VisGraph
from pyvisgraph.visible_vertices import edge_distance, visible_vertices
from pyvisgraph.viewer.loader import load_polygons

BENCHMARK_DIR = os.path.join(os.path.dirname(__file__), 'kml', 'benchmark')
N_PAIRS = 20
REPEATS = 3


def path_length(path):
    return sum(edge_distance(u, w) for u, w in zip(path[:-1], path[1:]))


def random_free_points(g, bounds, n, rng):
    """Sample n points inside bounds that are not inside any obstacle."""
    minx, miny, maxx, maxy = bounds
    points = []
    while len(points) < n:
        p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if g.point_in_polygon(p) == -1:
            points.append(p)
    return points


def time_query(g, origin, destination, algorithm):
    best = float('inf')
    path = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        path = g.shortest_path(origin, destination, algorithm=algorithm)
        best = min(best, time.perf_counter() - start)
    return best, path


def settled_nodes(g, origin, destination, algorithm):
    """Nodes settled by the search itself (origin/destination assumed built
    into the graph for counting purposes via the same temporary-edge path
    shortest_path uses)."""
    add_to_visg = Graph([])
    for v in visible_vertices(origin, g.graph, destination=destination):
        add_to_visg.add_edge(Edge(origin, v))
    for v in visible_vertices(destination, g.graph, origin=origin):
        add_to_visg.add_edge(Edge(destination, v))
    D, _ = algorithm(g.visgraph, origin, destination, add_to_visg)
    return len(D)


def main():
    maps = sorted(glob.glob(os.path.join(BENCHMARK_DIR, 'map_*.kml')))
    if not maps:
        raise SystemExit('No benchmark maps found; run '
                         'examples/generate_benchmark_kml.py first.')

    header = ('{:<10} {:>6} {:>6} {:>7} {:>12} {:>12} {:>8} '
              '{:>10} {:>10}').format(
        'map', 'polys', 'verts', 'edges', 'dijkstra_ms', 'astar_ms',
        'speedup', 'dij_nodes', 'ast_nodes')
    print(header)
    print('-' * len(header))

    for map_path in maps:
        result = load_polygons(map_path)
        g = VisGraph()
        g.build(result.polygons, workers=os.cpu_count() or 1, status=False)
        assert g.graph is not None and g.visgraph is not None
        n_verts = len(g.graph.get_points())
        n_edges = len(g.visgraph.get_edges())

        rng = random.Random(42)
        starts = random_free_points(g, result.bounds, N_PAIRS, rng)
        ends = random_free_points(g, result.bounds, N_PAIRS, rng)

        dij_time = ast_time = 0.0
        dij_nodes = ast_nodes = 0
        for origin, destination in zip(starts, ends):
            t_d, path_d = time_query(g, origin, destination, 'dijkstra')
            t_a, path_a = time_query(g, origin, destination, 'astar')
            assert abs(path_length(path_d) - path_length(path_a)) < 1e-9, \
                'path length mismatch on {}'.format(map_path)
            dij_time += t_d
            ast_time += t_a
            dij_nodes += settled_nodes(g, origin, destination, dijkstra)
            ast_nodes += settled_nodes(g, origin, destination, astar)

        n = N_PAIRS
        print('{:<10} {:>6} {:>6} {:>7} {:>12.3f} {:>12.3f} {:>7.2f}x '
              '{:>10.1f} {:>10.1f}'.format(
                  os.path.basename(map_path), len(result.polygons), n_verts,
                  n_edges, 1000 * dij_time / n, 1000 * ast_time / n,
                  dij_time / ast_time, dij_nodes / n, ast_nodes / n))


if __name__ == '__main__':
    main()
