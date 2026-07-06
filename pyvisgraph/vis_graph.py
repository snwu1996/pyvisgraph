"""
The MIT License (MIT)

Copyright (c) 2016 Christian August Reksten-Monsen

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
"""
from __future__ import annotations

import logging
import pickle
from collections.abc import Callable
from multiprocessing import Pool
from tqdm import tqdm

from pyvisgraph.graph import Graph, Edge, Point
from pyvisgraph.shortest_path import shortest_path
from pyvisgraph.visible_vertices import (visible_vertices, point_in_polygon,
                                         point_in_solid)
from pyvisgraph.visible_vertices import closest_point

logger = logging.getLogger(__name__)

# An exclusion frame is the extent of the map grown by this fraction of its
# larger side, so it strictly contains the navigable boundary. Its interior
# minus the navigable area is the off-limits solid; the four frame corners are
# the only vertices the inversion adds.
FRAME_MARGIN_FRAC = 0.05


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

    Returns a polygon (ring) list that, resolved by pyvisgraph's even-odd
    solidness rule, marks everything *outside* the ``boundary`` rings as solid
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


class VisGraph:

    def __init__(self):
        self.graph: Graph | None = None
        self.visgraph: Graph | None = None
        # The navigable boundary rings this graph was built with, or None for
        # an ordinary (non-inverted) map. Kept for reference/display; not
        # persisted by save().
        self.boundary: list[list[Point]] | None = None

    def load(self, filename: str):
        """Load obstacle graph and visibility graph. """
        with open(filename, 'rb') as load:
            self.graph, self.visgraph = pickle.load(load)

    def save(self, filename: str):
        """Save obstacle graph and visibility graph. """
        with open(filename, 'wb') as output:
            pickle.dump((self.graph, self.visgraph), output, -1)

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
        self.visgraph = Graph([])

        points = self.graph.get_points()
        batch_size = 10
        total = len(points)
        done = 0

        if workers == 1:
            for batch in tqdm([points[i:i + batch_size]
                               for i in range(0, len(points), batch_size)],
                            disable=not status):
                for edge in _vis_graph(self.graph, batch):
                    self.visgraph.add_edge(edge)
                done += len(batch)
                if progress is not None:
                    progress(done, total)
        else:
            pool = Pool(workers)
            batches = [(self.graph, points[i:i + batch_size])
                       for i in range(0, len(points), batch_size)]

            for i, result in enumerate(tqdm(
                    pool.imap(_vis_graph_wrapper, batches),
                    total=len(batches), disable=not status)):
                for edge in result:
                    self.visgraph.add_edge(edge)
                done += len(batches[i][1])
                if progress is not None:
                    progress(done, total)

    def find_visible(self, point: Point):
        """Find vertices visible from point."""

        if self.graph is None:
            logger.warning('call build() or load() first')
            return None
        return visible_vertices(point, self.graph)

    def update(self, points: list[Point], origin: Point | None = None,
               destination: Point | None = None):
        """Update visgraph by checking visibility of Points in list points."""

        if self.graph is None or self.visgraph is None:
            logger.warning('call build() or load() first')
            return None
        for p in points:
            for v in visible_vertices(p, self.graph, origin=origin,
                                      destination=destination):
                self.visgraph.add_edge(Edge(p, v))

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

        if self.graph is None or self.visgraph is None:
            logger.warning('call build() or load() first')
            return None
        origin_exists = origin in self.visgraph
        dest_exists = destination in self.visgraph
        if origin_exists and dest_exists:
            return shortest_path(self.visgraph, origin, destination,
                                 algorithm=algorithm)
        orgn = None if origin_exists else origin
        dest = None if dest_exists else destination
        add_to_visg = Graph([])
        if not origin_exists:
            for v in visible_vertices(origin, self.graph, destination=dest):
                add_to_visg.add_edge(Edge(origin, v))
        if not dest_exists:
            for v in visible_vertices(destination, self.graph, origin=orgn):
                add_to_visg.add_edge(Edge(destination, v))
        return shortest_path(self.visgraph, origin, destination, add_to_visg,
                             algorithm=algorithm)

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


def _vis_graph_wrapper(args: tuple[Graph, list[Point]]):
    try:
        return _vis_graph(*args)
    except KeyboardInterrupt:
        return []

def _vis_graph(graph: Graph, points: list[Point]):
    visible_edges = []
    for p1 in points:
        for p2 in visible_vertices(p1, graph, scan='half'):
            visible_edges.append(Edge(p1, p2))
    return visible_edges
