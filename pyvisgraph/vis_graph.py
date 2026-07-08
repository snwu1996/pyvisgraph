"""
The MIT License (MIT)

Copyright (c) 2016 Christian August Reksten-Monsen
Copyright (c) 2026 cvisgraph contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

VisGraph facade with the pyvisgraph API, backed by libcvisgraph. The
visibility edges are kept canonically as a set of coordinate pairs; the
Python `visgraph` Graph and the C path graph are materialized from it
lazily, so build -> shortest_path workflows never pay per-edge Python
object costs.

Note: save() writes a cvisgraph-specific pickle snapshot; pyvisgraph .pk1
files (which pickle pyvisgraph class instances) cannot be loaded.
"""
from __future__ import annotations

import ctypes
import logging
import pickle
from collections.abc import Callable

from tqdm import tqdm

from pyvisgraph import _clib
from pyvisgraph._clib import lib
from pyvisgraph.graph import Graph, Edge, Point
from pyvisgraph.shortest_path import PathGraph, _check_algorithm
from pyvisgraph.visible_vertices import (point_in_polygon, point_in_solid,
                                        closest_point)

logger = logging.getLogger(__name__)

# An exclusion frame is the extent of the map grown by this fraction of its
# larger side, so it strictly contains the navigable boundary. Its interior
# minus the navigable area is the off-limits solid; the four frame corners are
# the only vertices the inversion adds.
FRAME_MARGIN_FRAC = 0.05

Coord = tuple[float, float]
CoordEdge = tuple[Coord, Coord]


def _extent(rings: list[list[Point]]) -> tuple[float, float, float, float]:
    """Return (minx, miny, maxx, maxy) over every point in every ring."""
    xs = [p.x for ring in rings for p in ring]
    ys = [p.y for ring in rings for p in ring]
    if not xs:
        raise ValueError('cannot take the extent of an empty ring list')
    return min(xs), min(ys), max(xs), max(ys)


def boundary_frame(bounds: tuple[float, float, float, float],
                   margin_frac: float = FRAME_MARGIN_FRAC) -> list[Point]:
    """Return a counter-clockwise rectangle ring just outside *bounds*.

    *bounds* is (minx, miny, maxx, maxy). The rectangle is grown on every side
    by ``margin_frac`` of the larger extent so it strictly contains it.
    """
    minx, miny, maxx, maxy = bounds
    margin = margin_frac * max(maxx - minx, maxy - miny, 1e-9)
    return [Point(minx - margin, miny - margin),
            Point(maxx + margin, miny - margin),
            Point(maxx + margin, maxy + margin),
            Point(minx - margin, maxy + margin)]


def invert_boundary(obstacles: list[list[Point]], boundary: list[list[Point]],
                    bounds: tuple[float, float, float, float] | None = None,
                    margin_frac: float = FRAME_MARGIN_FRAC) -> list[list[Point]]:
    """Turn a navigable boundary into obstacle rings for an inverted map.

    Returns a polygon (ring) list that, resolved by the even-odd solidness
    rule, marks everything *outside* the ``boundary`` rings as solid
    off-limits space, the interior as free, and ``obstacles`` as solid islands
    inside it. An enclosing frame just outside ``bounds`` is prepended so the
    outside region is bounded; ``bounds`` defaults to the extent of the
    boundary and obstacle points.

    ``boundary`` may be several rings (an outer ring plus holes, as a shapely
    difference emits) and ``obstacles`` may be empty. The boundary and obstacle
    rings must not cross each other or the frame, the same non-crossing
    contract the visibility sweep places on ordinary polygons.
    """
    if bounds is None:
        bounds = _extent(boundary + obstacles)
    frame = boundary_frame(bounds, margin_frac)
    # Copy each ring so Graph's in-place closing-point pop does not mutate the
    # caller's boundary/obstacle lists.
    return ([frame] + [list(ring) for ring in boundary]
            + [list(ring) for ring in obstacles])


def _norm_edge(a: Coord, b: Coord) -> CoordEdge:
    """Canonical (sorted) form of an undirected coordinate edge."""
    return (a, b) if a <= b else (b, a)


class VisGraph:

    def __init__(self):
        self.graph: Graph | None = None
        # Canonical visibility edges as normalized coordinate pairs; the
        # Python Graph and the C path graph are derived from this lazily.
        self._vis_edges: set[CoordEdge] | None = None
        self._visgraph_py: Graph | None = None
        self._pathgraph: PathGraph | None = None
        # The navigable boundary rings this graph was built with, or None for
        # an ordinary (non-inverted) map. Kept for reference/display; not
        # persisted by save().
        self.boundary: list[list[Point]] | None = None

    @property
    def visgraph(self) -> Graph | None:
        """The visibility graph as a Graph, materialized on first access."""
        if self._visgraph_py is None and self._vis_edges is not None:
            pid = {}
            if self.graph is not None:
                pid = {(p.x, p.y): p.polygon_id
                       for p in self.graph.get_points()}
            g = Graph([])
            for a, b in self._vis_edges:
                g.add_edge(Edge(Point(a[0], a[1], pid.get(a, -1)),
                                Point(b[0], b[1], pid.get(b, -1))))
            self._visgraph_py = g
        return self._visgraph_py

    def load(self, filename: str):
        """Load obstacle graph and visibility graph. """
        with open(filename, 'rb') as load:
            state = pickle.load(load)
        graph = Graph([])
        points = [Point(x, y, poly) for x, y, poly in state['points']]
        for i, j in state['edges']:
            graph.add_edge(Edge(points[i], points[j]))
        for pid, edge_list in state['polygons'].items():
            graph.polygons[pid] = {Edge(points[i], points[j])
                                   for i, j in edge_list}
        self.graph = graph
        self._vis_edges = {_norm_edge(tuple(a), tuple(b))
                           for a, b in state['vis_edges']}
        self._visgraph_py = None
        self._pathgraph = None
        self.boundary = None

    def save(self, filename: str):
        """Save obstacle graph and visibility graph. """
        points = self.graph.get_points()
        index = {p: i for i, p in enumerate(points)}
        state = {
            'version': 1,
            'points': [(p.x, p.y, p.polygon_id) for p in points],
            'edges': [(index[e.p1], index[e.p2])
                      for e in self.graph.get_edges()],
            'polygons': {pid: [(index[e.p1], index[e.p2]) for e in edges]
                         for pid, edges in self.graph.polygons.items()},
            'vis_edges': [(a, b) for a, b in self._vis_edges],
        }
        with open(filename, 'wb') as output:
            pickle.dump(state, output, -1)

    def build(self, input: list[list[Point]],
              boundary: list[list[Point]] | None = None, workers: int = 1,
              status: bool = True,
              progress: Callable[[int, int], None] | None = None):
        """Build visibility graph based on a list of polygons.

        The input must be a list of polygons, where each polygon is a list of
        in-order (clockwise or counter clockwise) Points. It only one polygon,
        it must still be a list in a list, i.e. [[Point(0,0), Point(2,0),
        Point(2,1)]].
        If boundary is given (a navigable-region ring, or several rings), the
        map is inverted about it: everything outside the boundary becomes solid
        off-limits space, the interior is free, and the input polygons remain
        solid obstacle islands inside it. An enclosing frame is added
        automatically (see invert_boundary); the boundary and obstacle rings
        must not cross each other.
        Take advantage of processors with multiple cores by setting workers to
        the number of subprocesses you want. Defaults to 1, i.e. no subprocess
        will be started.
        Set status=False to turn off the statusbar when building.
        progress, if given, is called as progress(done, total) with the
        number of vertices whose visibility has been computed so far.
        """

        self.boundary = boundary
        if boundary is not None:
            input = invert_boundary(input, boundary)
        self.graph = Graph(input)
        cg = self.graph._to_c()

        total = len(cg.points)
        bar = tqdm(total=total, disable=not status)
        last = [0]

        def _cb(done, _total, _ud):
            bar.update(done - last[0])
            last[0] = done
            if progress is not None:
                progress(done, total)

        cb = _clib.PROGRESS_FN(_cb)
        try:
            out = _clib.c_int32_p()
            n = lib.cvg_build(cg.handle, workers, cb, None,
                              ctypes.byref(out))
        finally:
            bar.close()
        if n < 0:
            raise MemoryError('cvg_build failed')

        vis_edges = set()
        pts = cg.points
        for i in range(n):
            a, b = pts[out[i * 2]], pts[out[i * 2 + 1]]
            vis_edges.add(_norm_edge((a.x, a.y), (b.x, b.y)))
        if out:
            lib.cvg_free(out)

        self._vis_edges = vis_edges
        self._visgraph_py = None
        self._pathgraph = None

    def find_visible(self, point: Point):
        """Find vertices visible from point."""

        if self.graph is None:
            logger.warning('call build() or load() first')
            return None
        return self.graph._to_c().visible_points(point.x, point.y)

    def update(self, points: list[Point], origin: Point | None = None,
               destination: Point | None = None):
        """Update visgraph by checking visibility of Points in list points."""

        if self.graph is None or self._vis_edges is None:
            logger.warning('call build() or load() first')
            return None
        cg = self.graph._to_c()
        for p in points:
            for v in cg.visible_points(p.x, p.y, origin=origin,
                                       destination=destination):
                self._vis_edges.add(_norm_edge((p.x, p.y), (v.x, v.y)))
        self._visgraph_py = None
        self._pathgraph = None

    def _ensure_pathgraph(self) -> PathGraph:
        if self._pathgraph is None:
            self._pathgraph = PathGraph(sorted(self._vis_edges))
        return self._pathgraph

    def shortest_path(self, origin: Point, destination: Point,
                      algorithm: str = 'astar'):
        """Find and return shortest path between origin and destination.

        Will return in-order list of Points of the shortest path found. If
        origin or destination are not in the visibility graph, their respective
        visibility edges will be found, but only kept temporarily for finding
        the shortest path.
        Searches with A* by default; pass algorithm='dijkstra' for the
        original Dijkstra search. Both return an optimal path. Returns an
        empty list when no path exists between origin and destination.
        """

        if self.graph is None or self._vis_edges is None:
            logger.warning('call build() or load() first')
            return None
        _check_algorithm(algorithm)
        pg = self._ensure_pathgraph()
        cg = self.graph._to_c()

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

        origin_exists = pg.find((origin.x, origin.y)) >= 0
        dest_exists = pg.find((destination.x, destination.y)) >= 0
        o_node = node((origin.x, origin.y))
        d_node = node((destination.x, destination.y))
        orgn = None if origin_exists else origin
        dest = None if dest_exists else destination
        if not origin_exists:
            for x, y, _v in cg.visible_from(origin.x, origin.y,
                                            destination=dest):
                extra_edges.append((o_node, node((x, y))))
        if not dest_exists:
            for x, y, _v in cg.visible_from(destination.x, destination.y,
                                            origin=orgn):
                extra_edges.append((d_node, node((x, y))))

        path = pg.shortest(o_node, d_node, extra_nodes, extra_edges,
                           algorithm)
        return [Point(x, y) for x, y in path]

    def point_in_polygon(self, point: Point):
        """Return polygon_id if point in a polygon, -1 otherwise."""

        if self.graph is None:
            logger.warning('call build() or load() first')
            return None
        return point_in_polygon(point, self.graph)

    def point_in_solid(self, point: Point):
        """Return True if point is in solid obstacle space (even-odd rule).

        A point interior to an odd number of polygons is solid; the hole of
        a donut-shaped obstacle counts twice and is therefore free space,
        unlike point_in_polygon which reports it as inside the outer ring.
        """

        if self.graph is None:
            logger.warning('call build() or load() first')
            return None
        return point_in_solid(point, self.graph)

    def closest_point(self, point: Point, polygon_id: int,
                      length: float = 0.001):
        """Return closest Point outside polygon from point.

        Note method assumes point is inside the polygon, no check is
        performed.
        """

        if self.graph is None:
            logger.warning('call build() or load() first')
            return None
        return closest_point(point, self.graph, polygon_id, length)
