"""Drop-in equivalents of pyvisgraph.visible_vertices, each a thin wrapper
over the same libcvisgraph routines the sweep itself uses, so helper results
and sweep results can never disagree.

See graph.py for the license.
"""
from __future__ import annotations

import ctypes
from typing import Iterable

from pyvisgraph._clib import lib
from pyvisgraph.graph import Edge, Graph, Point

INF = 10000
CCW = 1
CW = -1
COLLINEAR = 0
"""Due to floating point representation error, some functions need to
   truncate floating point numbers to a certain tolerance."""
COLIN_TOLERANCE = 10
T = 10 ** COLIN_TOLERANCE
T2 = 10.0 ** COLIN_TOLERANCE


def visible_vertices(point: Point, graph: Graph, origin: Point | None = None,
                     destination: Point | None = None,
                     scan: str = 'full') -> list[Point]:
    """Returns list of Points in graph visible by point.

    If origin and/or destination Points are given, these will also be checked
    for visibility. scan 'full' will check for visibility against all points in
    graph, 'half' will check for visibility against half the points. This saves
    running time when building a complete visibility graph, as the points
    that are not checked will eventually be 'point'.
    """
    return graph._to_c().visible_points(point.x, point.y, origin, destination,
                                        scan_half=(scan == 'half'))


def polygon_crossing(p1: Point, poly_edges: Iterable[Edge]) -> bool:
    """Returns True if Point p1 is internal to the polygon. The polygon is
    defined by the Edges in poly_edges. Uses crossings algorithm and takes into
    account edges that are collinear to p1."""
    intersect_count = 0
    for edge in poly_edges:
        if p1.y < edge.p1.y and p1.y < edge.p2.y:
            continue
        if p1.y > edge.p1.y and p1.y > edge.p2.y:
            continue
        if p1.x > edge.p1.x and p1.x > edge.p2.x:
            continue
        edge_p1_collinear = (ccw(p1, edge.p1, Point(INF, p1.y)) == COLLINEAR)
        edge_p2_collinear = (ccw(p1, edge.p2, Point(INF, p1.y)) == COLLINEAR)
        if edge_p1_collinear and edge_p2_collinear:
            continue
        if edge_p1_collinear or edge_p2_collinear:
            collinear_point = edge.p1 if edge_p1_collinear else edge.p2
            if edge.get_adjacent(collinear_point).y > p1.y:
                intersect_count += 1
        elif edge_intersect(p1, Point(INF, p1.y), edge):
            intersect_count += 1
    return intersect_count % 2 != 0


def point_in_solid(p: Point, graph: Graph) -> bool:
    """Return True if p is in solid obstacle space, i.e. interior to an odd
    number of polygons (even-odd rule). The hole ring of a donut-shaped
    obstacle contains its courtyard twice, so the courtyard is free space."""
    return bool(lib.cvg_point_in_solid(graph._to_c().handle, p.x, p.y))


def edge_in_polygon(p1: Point, p2: Point, graph: Graph) -> bool:
    """Return true if the edge from p1 to p2 passes through solid obstacle
    space, tested at the edge mid-point with the even-odd rule."""
    mid_point = Point((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
    return point_in_solid(mid_point, graph)


def point_in_polygon(p: Point, graph: Graph) -> int:
    """Return the polygon id p is interior to, -1 otherwise."""
    cg = graph._to_c()
    idx = lib.cvg_point_in_polygon(cg.handle, p.x, p.y)
    return cg.poly_keys[idx] if idx >= 0 else -1


def unit_vector(c: Point, p: Point) -> Point:
    magnitude = edge_distance(c, p)
    return Point((p.x - c.x) / magnitude, (p.y - c.y) / magnitude)


def closest_point(p: Point, graph: Graph, polygon_id: int,
                  length: float = 0.001) -> Point:
    """Assumes p is interior to the polygon with polygon_id. Returns the
    closest point c outside the polygon to p, where the distance from c to
    the intersect point from p to the edge of the polygon is length."""
    cg = graph._to_c()
    pidx = cg.poly_keys.index(polygon_id)
    ox = ctypes.c_double()
    oy = ctypes.c_double()
    if not lib.cvg_closest_point(cg.handle, p.x, p.y, pidx, length,
                                 ctypes.byref(ox), ctypes.byref(oy)):
        raise AssertionError('polygon has no edges')
    return Point(ox.value, oy.value)


def edge_distance(p1: Point, p2: Point) -> float:
    """Return the Euclidean distance between two Points."""
    return lib.cvg_edge_distance(p1.x, p1.y, p2.x, p2.y)


def intersect_point(p1: Point, p2: Point, edge: Edge) -> Point | None:
    """Return intersect Point where the edge from p1, p2 intersects edge"""
    ox = ctypes.c_double()
    oy = ctypes.c_double()
    if lib.cvg_intersect_point(p1.x, p1.y, p2.x, p2.y,
                               edge.p1.x, edge.p1.y, edge.p2.x, edge.p2.y,
                               ctypes.byref(ox), ctypes.byref(oy)):
        return Point(ox.value, oy.value)
    return None


def point_edge_distance(p1: Point, p2: Point, edge: Edge) -> float:
    """Return the Eucledian distance from p1 to intersect point with edge.
    Assumes the line going from p1 to p2 intersects edge before reaching p2."""
    return lib.cvg_point_edge_distance(p1.x, p1.y, p2.x, p2.y,
                                       edge.p1.x, edge.p1.y,
                                       edge.p2.x, edge.p2.y)


def angle(center: Point, point: Point) -> float:
    """Return the angle (radian) of point from center of the radian circle."""
    return lib.cvg_angle(center.x, center.y, point.x, point.y)


def angle2(point_a: Point, point_b: Point, point_c: Point) -> float:
    """Return angle B (radian) between point_b and point_c."""
    return lib.cvg_angle2(point_a.x, point_a.y, point_b.x, point_b.y,
                          point_c.x, point_c.y)


def ccw(A: Point, B: Point, C: Point) -> int:
    """Return 1 if counter clockwise, -1 if clock wise, 0 if collinear """
    return lib.cvg_ccw(A.x, A.y, B.x, B.y, C.x, C.y)


def on_segment(p: Point, q: Point, r: Point) -> bool:
    """Given three colinear points p, q, r, the function checks if point q
    lies on line segment 'pr'."""
    return bool(lib.cvg_on_segment(p.x, p.y, q.x, q.y, r.x, r.y))


def edge_intersect(p1: Point, q1: Point, edge: Edge) -> bool:
    """Return True if edge from A, B interects edge."""
    return bool(lib.cvg_edge_intersect(p1.x, p1.y, q1.x, q1.y,
                                       edge.p1.x, edge.p1.y,
                                       edge.p2.x, edge.p2.y))
