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

Point, Edge and Graph are pure-Python containers with the exact semantics of
pyvisgraph.graph; the geometry algorithms that consume them run in
libcvisgraph via the cached _CGraph conversion.
"""
from __future__ import annotations

import ctypes
from collections import defaultdict

from pyvisgraph import _clib
from pyvisgraph._clib import lib


class Point:
    __slots__ = ('x', 'y', 'polygon_id')

    x: float
    y: float
    polygon_id: int

    def __init__(self, x: float, y: float, polygon_id: int = -1) -> None:
        self.x = float(x)
        self.y = float(y)
        self.polygon_id = polygon_id

    def __eq__(self, point: object) -> bool:
        return (isinstance(point, Point)
                and self.x == point.x and self.y == point.y)

    def __ne__(self, point: object) -> bool:
        return not self.__eq__(point)

    def __lt__(self, point: Point) -> bool:
        """ This is only needed for shortest path calculations where heapq is
            used. When there are two points of equal distance, heapq will
            instead evaluate the Points, which doesnt work in Python 3 and
            throw a TypeError."""
        return hash(self) < hash(point)

    def __str__(self) -> str:
        return "(%.2f, %.2f)" % (self.x, self.y)

    def __hash__(self) -> int:
        return self.x.__hash__() ^ self.y.__hash__()

    def __repr__(self) -> str:
        return "Point(%.2f, %.2f)" % (self.x, self.y)


class Edge:
    __slots__ = ('p1', 'p2')

    p1: Point
    p2: Point

    def __init__(self, point1: Point, point2: Point) -> None:
        self.p1 = point1
        self.p2 = point2

    def get_adjacent(self, point: Point) -> Point:
        if point == self.p1:
            return self.p2
        return self.p1

    def __contains__(self, point: Point) -> bool:
        return self.p1 == point or self.p2 == point

    def __eq__(self, edge: object) -> bool:
        if not isinstance(edge, Edge):
            return False
        if self.p1 == edge.p1 and self.p2 == edge.p2:
            return True
        if self.p1 == edge.p2 and self.p2 == edge.p1:
            return True
        return False

    def __ne__(self, edge: object) -> bool:
        return not self.__eq__(edge)

    def __str__(self) -> str:
        return "({}, {})".format(self.p1, self.p2)

    def __repr__(self) -> str:
        return "Edge({!r}, {!r})".format(self.p1, self.p2)

    def __hash__(self) -> int:
        return self.p1.__hash__() ^ self.p2.__hash__()


class _CGraph:
    """Owner of a cvg_graph handle plus the index maps needed to translate
    between Point objects and C vertex/polygon indices."""

    def __init__(self, graph: 'Graph') -> None:
        points = graph.get_points()
        index = {p: i for i, p in enumerate(points)}
        edges = list(graph.get_edges())
        edge_index = {e: i for i, e in enumerate(edges)}
        xy = _clib.as_double_array(
            [c for p in points for c in (p.x, p.y)])
        pairs = _clib.as_int32_array(
            [i for e in edges for i in (index[e.p1], index[e.p2])])

        poly_keys = sorted(graph.polygons)
        offsets = [0]
        poly_edges: list[int] = []
        for pid in poly_keys:
            poly_edges.extend(edge_index[e] for e in graph.polygons[pid])
            offsets.append(len(poly_edges))
        offs = _clib.as_int32_array(offsets)
        pedges = _clib.as_int32_array(poly_edges)

        handle = lib.cvg_graph_new(len(points), xy, len(edges), pairs,
                                   len(poly_keys), offs, pedges)
        if not handle:
            raise ValueError('invalid graph data')
        self.handle = handle
        self.points = points          # C vertex index -> canonical Point
        self.poly_keys = poly_keys    # C polygon index -> Graph polygon id

    def __del__(self):
        handle = getattr(self, 'handle', None)
        if handle:
            try:
                lib.cvg_graph_free(handle)
            except (AttributeError, TypeError):
                pass  # interpreter shutdown

    def visible_from(self, px: float, py: float, origin: Point | None = None,
                     destination: Point | None = None,
                     scan_half: bool = False) -> list[tuple[float, float, int]]:
        """Run the sweep; returns (x, y, vertex index or -1) tuples."""
        o = _clib.as_double_array([origin.x, origin.y]) if origin else None
        d = (_clib.as_double_array([destination.x, destination.y])
             if destination else None)
        out = ctypes.POINTER(_clib.VisPt)()
        n = lib.cvg_visible_from(self.handle, px, py, o, d,
                                 1 if scan_half else 0, ctypes.byref(out))
        if n < 0:
            raise MemoryError('cvg_visible_from failed')
        result = [(out[i].x, out[i].y, out[i].vertex) for i in range(n)]
        lib.cvg_free(out)
        return result

    def visible_points(self, px: float, py: float,
                       origin: Point | None = None,
                       destination: Point | None = None,
                       scan_half: bool = False) -> list[Point]:
        """Like visible_from, but resolves graph vertices to their canonical
        Point objects (the ones pyvisgraph would return)."""
        result = []
        for x, y, vertex in self.visible_from(px, py, origin, destination,
                                              scan_half):
            result.append(self.points[vertex] if vertex >= 0 else Point(x, y))
        return result


class Graph:
    """
    A Graph is represented by a dict where the keys are Points in the Graph
    and the dict values are sets containing Edges incident on each Point.
    A separate set *edges* contains all Edges in the graph.

    The input must be a list of polygons, where each polygon is a list of
    in-order (clockwise or counter clockwise) Points. If only one polygon,
    it must still be a list in a list, i.e. [[Point(0,0), Point(2,0),
    Point(2,1)]].

    *polygons* dictionary: key is a integer polygon ID and values are the
    edges that make up the polygon. Note only polygons with 3 or more Points
    will be classified as a polygon. Non-polygons like just one Point will be
    given a polygon ID of -1 and not maintained in the dict.
    """

    def __init__(self, polygons: list[list[Point]]) -> None:
        self.graph: defaultdict[Point, set[Edge]] = defaultdict(set)
        self.edges: set[Edge] = set()
        self.polygons: defaultdict[int, set[Edge]] = defaultdict(set)
        self._c: _CGraph | None = None
        pid = 0
        for polygon in polygons:
            if polygon[0] == polygon[-1] and len(polygon) > 1:
                polygon.pop()
            for i, point in enumerate(polygon):
                sibling_point = polygon[(i + 1) % len(polygon)]
                edge = Edge(point, sibling_point)
                if len(polygon) > 2:
                    point.polygon_id = pid
                    sibling_point.polygon_id = pid
                    self.polygons[pid].add(edge)
                self.add_edge(edge)
            if len(polygon) > 2:
                pid += 1

    def get_adjacent_points(self, point: Point) -> list[Point]:
        return [edge.get_adjacent(point) for edge in self[point]]

    def get_points(self) -> list[Point]:
        return list(self.graph)

    def get_edges(self) -> set[Edge]:
        return self.edges

    def add_edge(self, edge: Edge) -> None:
        self.graph[edge.p1].add(edge)
        self.graph[edge.p2].add(edge)
        self.edges.add(edge)
        self._c = None  # invalidate the cached C conversion

    def _to_c(self) -> _CGraph:
        if self._c is None:
            self._c = _CGraph(self)
        return self._c

    def __contains__(self, item: object) -> bool:
        if isinstance(item, Point):
            return item in self.graph
        if isinstance(item, Edge):
            return item in self.edges
        return False

    def __getitem__(self, point: Point) -> set[Edge]:
        if point in self.graph:
            return self.graph[point]
        return set()

    def __str__(self) -> str:
        res = ""
        for point in self.graph:
            res += "\n" + str(point) + ": "
            for edge in self.graph[point]:
                res += str(edge)
        return res

    def __repr__(self) -> str:
        return self.__str__()
