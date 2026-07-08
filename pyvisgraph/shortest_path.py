"""Shortest path over a visibility graph, running in libcvisgraph.

The module-level shortest_path() mirrors pyvisgraph.shortest_path (Graph in,
list of Points out, optional add_to_visgraph with temporary edges); PathGraph
is the reusable C-side structure VisGraph caches between queries.

See graph.py for the license.
"""
from __future__ import annotations

import ctypes

from pyvisgraph import _clib
from pyvisgraph._clib import lib
from pyvisgraph.graph import Graph, Point
from pyvisgraph.visible_vertices import edge_distance

_ALGORITHMS = ('astar', 'dijkstra')

Coord = tuple[float, float]


def path_length(path: list[Point]) -> float:
    """Return the total Euclidean length of an in-order list of Points.

    This is the sum of the straight-line distances between consecutive points,
    i.e. the planar cost that shortest_path minimizes. Returns 0.0 for a path
    with fewer than two points.
    """
    return sum(edge_distance(p1, p2) for p1, p2 in zip(path, path[1:]))


class PathGraph:
    """C-side node/edge structure for shortest-path queries.

    Nodes are the unique endpoints of the visibility edges (exactly the
    points a pyvisgraph visibility Graph has as keys); temporary
    origin/destination nodes and edges are passed per query.
    """

    def __init__(self, edges: list[tuple[Coord, Coord]]) -> None:
        node_index: dict[Coord, int] = {}
        coords: list[float] = []
        pairs: list[int] = []

        def node(c: Coord) -> int:
            idx = node_index.get(c)
            if idx is None:
                idx = len(node_index)
                node_index[c] = idx
                coords.extend(c)
            return idx

        for a, b in edges:
            pairs.append(node(a))
            pairs.append(node(b))

        self.n = len(node_index)
        self._coords = coords
        handle = lib.cvg_pathgraph_new(
            self.n, _clib.as_double_array(coords),
            len(edges), _clib.as_int32_array(pairs))
        if not handle:
            raise ValueError('invalid path graph data')
        self.handle = handle

    def __del__(self):
        handle = getattr(self, 'handle', None)
        if handle:
            try:
                lib.cvg_pathgraph_free(handle)
            except (AttributeError, TypeError):
                pass  # interpreter shutdown

    def find(self, c: Coord) -> int:
        return lib.cvg_pathgraph_find(self.handle, c[0], c[1])

    def shortest(self, origin: int, dest: int, extra_nodes: list[Coord],
                 extra_edges: list[tuple[int, int]],
                 algorithm: str) -> list[Coord]:
        """Return the path as coordinates; empty when unreachable."""
        exy = _clib.as_double_array([v for c in extra_nodes for v in c])
        epairs = _clib.as_int32_array([i for e in extra_edges for i in e])
        out = _clib.c_int32_p()
        n = lib.cvg_pathgraph_shortest(
            self.handle, origin, dest, len(extra_nodes), exy,
            len(extra_edges), epairs, 1 if algorithm == 'astar' else 0,
            ctypes.byref(out))
        if n < 0:
            raise ValueError('shortest path query failed')
        path = []
        for i in range(n):
            node = out[i]
            if node < self.n:
                path.append((self._coords[2 * node],
                             self._coords[2 * node + 1]))
            else:
                path.append(extra_nodes[node - self.n])
        if out:
            lib.cvg_free(out)
        return path


def _check_algorithm(algorithm: str) -> None:
    if algorithm not in _ALGORITHMS:
        raise ValueError("unknown algorithm: {}".format(algorithm))


def shortest_path(graph: Graph, origin: Point, destination: Point,
                  add_to_visgraph: Graph | None = None,
                  algorithm: str = 'astar') -> list[Point]:
    _check_algorithm(algorithm)
    pg = PathGraph([((e.p1.x, e.p1.y), (e.p2.x, e.p2.y))
                    for e in graph.get_edges()])

    extra_nodes: list[Coord] = []
    extra_edges: list[tuple[int, int]] = []

    def node(c: Coord) -> int:
        idx = pg.find(c)
        if idx >= 0:
            return idx
        for i, existing in enumerate(extra_nodes):
            if existing == c:
                return pg.n + i
        extra_nodes.append(c)
        return pg.n + len(extra_nodes) - 1

    o_node = node((origin.x, origin.y))
    d_node = node((destination.x, destination.y))
    if add_to_visgraph is not None:
        for e in add_to_visgraph.get_edges():
            extra_edges.append((node((e.p1.x, e.p1.y)),
                                node((e.p2.x, e.p2.y))))

    path = pg.shortest(o_node, d_node, extra_nodes, extra_edges, algorithm)
    return [Point(x, y) for x, y in path]
