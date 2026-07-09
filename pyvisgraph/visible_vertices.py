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

from math import pi, sqrt, atan, acos
from typing import Iterable

from pyvisgraph.graph import Edge, Graph, Point

INF = 10000
CCW = 1
CW = -1
COLLINEAR = 0
"""Due to floating point representation error, some functions need to
   truncate floating point numbers to a certain tolerance."""
COLIN_TOLERANCE = 10
T = 10**COLIN_TOLERANCE
T2 = 10.0**COLIN_TOLERANCE

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
    edges = graph.get_edges()
    points = graph.get_points()
    if origin: points.append(origin)
    if destination: points.append(destination)
    _sort_scan_points(point, points, scan)

    # Initialize open_edges with any intersecting edges on the half line from
    # point along the positive x-axis
    open_edges = OpenEdges()
    point_inf = Point(INF, point.y)
    for edge in edges:
        if point in edge: continue
        if edge_intersect(point, point_inf, edge):
            if on_segment(point, edge.p1, point_inf): continue
            if on_segment(point, edge.p2, point_inf): continue
            open_edges.insert(point, point_inf, edge)

    visible = []
    prev = None
    prev_visible = None
    for p in points:
        if p == point: continue
        if scan == 'half' and angle(point, p) > pi: break

        # Update open_edges - remove clock wise edges incident on p
        if open_edges:
            for edge in graph[p]:
                if ccw(point, p, edge.get_adjacent(p)) == CW:
                    open_edges.delete(point, p, edge)

        # Check if p is visible from point
        is_visible = False
        # ...Non-collinear points
        if prev is None or ccw(point, prev, p) != COLLINEAR or not on_segment(point, prev, p):
            if len(open_edges) == 0:
                is_visible = True
            elif not edge_intersect(point, p, open_edges.smallest()):
                is_visible = True
        # ...For collinear points, if previous point was not visible, p is not
        elif not prev_visible:
            is_visible = False
        # ...For collinear points, if previous point was visible, need to check
        # that the edge from prev to p does not intersect any open edge.
        else:
            is_visible = True
            for edge in open_edges:
                if prev not in edge and edge_intersect(prev, p, edge):
                    is_visible = False
                    break
            if is_visible and edge_in_polygon(prev, p, graph):
                    is_visible = False

        # Check if the visible edge is interior to its polygon
        if is_visible and p not in graph.get_adjacent_points(point):
            is_visible = not edge_in_polygon(point, p, graph)

        if is_visible: visible.append(p)

        # Update open_edges - Add counter clock wise edges incident on p
        for edge in graph[p]:
            if (point not in edge) and ccw(point, p, edge.get_adjacent(p)) == CCW:
                open_edges.insert(point, p, edge)

        prev = p
        prev_visible = is_visible
    return visible


def _sort_scan_points(point: Point, points: list[Point], scan: str) -> None:
    """Sort *points* in place into rotational-sweep order around *point*.

    Primary order is angle then distance, but the distance tie-break must
    fire for every group of points the sweep's occlusion logic treats as
    collinear (ccw at COLIN_TOLERANCE), not only for bit-identical angles:
    buffered geometry routinely places several vertices along one straight
    line, and their angles from a fourth point on that line differ by float
    noise. Scanning a far same-ray point before the near one whose incident
    edges occlude it bypasses the collinear occlusion logic and admits
    visibility edges through solid space. Same-ray points end up adjacent in
    the angle-sorted list, so each run of consecutive ccw-collinear,
    same-direction points is re-sorted near to far. A 'half' scan stops at
    angle pi, so runs there keep past-pi members behind the cutoff instead
    of pulling them in front of points the scan must still process.
    """
    points.sort(key=lambda p: (angle(point, p), edge_distance(point, p)))
    i, n = 0, len(points)
    while i < n:
        j = i + 1
        while (j < n
               and ccw(point, points[j - 1], points[j]) == COLLINEAR
               and ((points[j - 1].x - point.x) * (points[j].x - point.x)
                    + (points[j - 1].y - point.y)
                    * (points[j].y - point.y)) > 0):
            j += 1
        if j - i > 1:
            if scan == 'half':
                key = lambda p: (angle(point, p) > pi,
                                 edge_distance(point, p))
            else:
                key = lambda p: edge_distance(point, p)
            points[i:j] = sorted(points[i:j], key=key)
        i = j


def polygon_crossing(p1: Point, poly_edges: Iterable[Edge]) -> bool:
    """Returns True if Point p1 is internal to the polygon. The polygon is
    defined by the Edges in poly_edges. Uses crossings algorithm and takes into
    account edges that are collinear to p1."""
    p2 = Point(INF, p1.y)
    intersect_count = 0
    for edge in poly_edges:
        if p1.y < edge.p1.y and p1.y < edge.p2.y: continue
        if p1.y > edge.p1.y and p1.y > edge.p2.y: continue
        if p1.x > edge.p1.x and p1.x > edge.p2.x: continue
        # Deal with points collinear to p1
        edge_p1_collinear = (ccw(p1, edge.p1, p2) == COLLINEAR)
        edge_p2_collinear = (ccw(p1, edge.p2, p2) == COLLINEAR)
        if edge_p1_collinear and edge_p2_collinear: continue
        if edge_p1_collinear or edge_p2_collinear:
            collinear_point = edge.p1 if edge_p1_collinear else edge.p2
            if edge.get_adjacent(collinear_point).y > p1.y:
                intersect_count += 1
        elif edge_intersect(p1, p2, edge):
            intersect_count += 1
    if intersect_count % 2 == 0:
        return False
    return True


def _polygon_bounds(
        graph: Graph) -> dict[int, tuple[float, float, float, float]]:
    """Return {polygon_id: (minx, miny, maxx, maxy)}, cached on the graph.

    Computed lazily (rather than in Graph.__init__) so graphs unpickled
    from files saved before this cache existed keep working.
    """
    bounds = getattr(graph, '_polygon_bounds', None)
    if bounds is None:
        bounds = {}
        for polygon_id, edges in graph.polygons.items():
            xs = [x for edge in edges for x in (edge.p1.x, edge.p2.x)]
            ys = [y for edge in edges for y in (edge.p1.y, edge.p2.y)]
            bounds[polygon_id] = (min(xs), min(ys), max(xs), max(ys))
        graph._polygon_bounds = bounds
    return bounds


def point_in_solid(p: Point, graph: Graph) -> bool:
    """Return True if p is in solid obstacle space, i.e. interior to an odd
    number of polygons (even-odd rule). The hole ring of a donut-shaped
    obstacle contains its courtyard twice, so the courtyard is free space."""
    crossings = 0
    for polygon_id, (minx, miny, maxx, maxy) in _polygon_bounds(graph).items():
        if not (minx <= p.x <= maxx and miny <= p.y <= maxy):
            continue
        if polygon_crossing(p, graph.polygons[polygon_id]):
            crossings += 1
    return crossings % 2 == 1


def edge_in_polygon(p1: Point, p2: Point, graph: Graph) -> bool:
    """Return true if the edge from p1 to p2 passes through solid obstacle
    space, tested at the edge mid-point with the even-odd rule. Assumes the
    edge does not cross any polygon edge (the sweep checks that), so the
    mid-point decides the whole segment."""
    mid_point = Point((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
    return point_in_solid(mid_point, graph)


def point_in_polygon(p: Point, graph: Graph) -> int:
    """Return true if the point p is interior to any polygon in graph."""
    for polygon in graph.polygons:
        if polygon_crossing(p, graph.polygons[polygon]):
            return polygon
    return -1


def unit_vector(c: Point, p: Point) -> Point:
    magnitude = edge_distance(c, p)
    return Point((p.x - c.x) / magnitude, (p.y - c.y) / magnitude)


def closest_point(p: Point, graph: Graph, polygon_id: int,
                  length: float = 0.001) -> Point:
    """Assumes p is interior to the polygon with polygon_id. Returns the
    closest point c outside the polygon to p, where the distance from c to
    the intersect point from p to the edge of the polygon is length."""
    polygon_edges = graph.polygons[polygon_id]
    close_point: Point | None = None
    close_edge: Edge | None = None
    close_dist = float('inf')
    # Finds point closest to p, but on a edge of the polygon.
    # Solution from http://stackoverflow.com/a/6177788/4896361
    for e in polygon_edges:
        num = ((p.x-e.p1.x)*(e.p2.x-e.p1.x) + (p.y-e.p1.y)*(e.p2.y-e.p1.y))
        denom = ((e.p2.x - e.p1.x)**2 + (e.p2.y - e.p1.y)**2)
        u = num/denom
        pu = Point(e.p1.x + u*(e.p2.x - e.p1.x), e.p1.y + u*(e.p2.y- e.p1.y))
        pc = pu
        if u < 0:
            pc = e.p1
        elif u > 1:
            pc = e.p2
        d = edge_distance(p, pc)
        if d < close_dist:
            close_dist = d
            close_point = pc
            close_edge = e
    assert close_point is not None and close_edge is not None, \
        'polygon has no edges'

    # Extend the newly found point so it is outside the polygon by `length`.
    if close_point in close_edge:
        c = close_edge.p1 if close_point == close_edge.p1 else close_edge.p2
        edges = list(graph[c])
        v1 = unit_vector(c, edges[0].get_adjacent(c))
        v2 = unit_vector(c, edges[1].get_adjacent(c))
        vsum = unit_vector(Point(0, 0), Point(v1.x + v2.x, v1.y + v2.y))
        close1 = Point(c.x + (vsum.x * length), c.y + (vsum.y * length))
        close2 = Point(c.x - (vsum.x * length), c.y - (vsum.y * length))
        if point_in_polygon(close1, graph) == -1:
            return close1
        return close2
    else:
        v = unit_vector(p, close_point)
        return Point(close_point.x + v.x*length, close_point.y + v.y*length)


def edge_distance(p1: Point, p2: Point) -> float:
    """Return the Euclidean distance between two Points."""
    return sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)


def intersect_point(p1: Point, p2: Point, edge: Edge) -> Point | None:
    """Return intersect Point where the edge from p1, p2 intersects edge"""
    if p1 in edge: return p1
    if p2 in edge: return p2
    if edge.p1.x == edge.p2.x:
        if p1.x == p2.x:
            return None
        pslope = (p1.y - p2.y) / (p1.x - p2.x)
        intersect_x = edge.p1.x
        intersect_y = pslope * (intersect_x - p1.x) + p1.y
        return Point(intersect_x, intersect_y)

    if p1.x == p2.x:
        eslope = (edge.p1.y - edge.p2.y) / (edge.p1.x - edge.p2.x)
        intersect_x = p1.x
        intersect_y = eslope * (intersect_x - edge.p1.x) + edge.p1.y
        return Point(intersect_x, intersect_y)

    pslope = (p1.y - p2.y) / (p1.x - p2.x)
    eslope = (edge.p1.y - edge.p2.y) / (edge.p1.x - edge.p2.x)
    if eslope == pslope:
        return None
    intersect_x = (eslope * edge.p1.x - pslope * p1.x + p1.y - edge.p1.y) / (eslope - pslope)
    intersect_y = eslope * (intersect_x - edge.p1.x) + edge.p1.y
    return Point(intersect_x, intersect_y)


def point_edge_distance(p1: Point, p2: Point, edge: Edge) -> float:
    """Return the Eucledian distance from p1 to intersect point with edge.
    Assumes the line going from p1 to p2 intersects edge before reaching p2."""
    ip = intersect_point(p1, p2, edge)
    if ip is not None:
        return edge_distance(p1, ip)
    return 0


def angle(center: Point, point: Point) -> float:
    """Return the angle (radian) of point from center of the radian circle.
     ------p
     |   /
     |  /
    c|a/
    """
    dx = point.x - center.x
    dy = point.y - center.y
    if dx == 0:
        if dy < 0:
            return pi * 3 / 2
        return pi / 2
    if dy == 0:
        if dx < 0:
            return pi
        return 0
    if dx < 0:
        return pi + atan(dy / dx)
    if dy < 0:
        return 2 * pi + atan(dy / dx)
    return atan(dy / dx)


def angle2(point_a: Point, point_b: Point, point_c: Point) -> float:
    """Return angle B (radian) between point_b and point_c.
           c
         /  \
       /    B\
      a-------b
    """
    a = (point_c.x - point_b.x)**2 + (point_c.y - point_b.y)**2
    b = (point_c.x - point_a.x)**2 + (point_c.y - point_a.y)**2
    c = (point_b.x - point_a.x)**2 + (point_b.y - point_a.y)**2
    cos_value = (a + c - b) / (2 * sqrt(a) * sqrt(c))
    return acos(int(cos_value*T)/T2)


def ccw(A: Point, B: Point, C: Point) -> int:
    """Return 1 if counter clockwise, -1 if clock wise, 0 if collinear """
    #  Rounding this way is faster than calling round()
    area = int(((B.x - A.x) * (C.y - A.y) - (B.y - A.y) * (C.x - A.x))*T)/T2
    if area > 0: return 1
    if area < 0: return -1
    return 0


def on_segment(p: Point, q: Point, r: Point) -> bool:
    """Given three colinear points p, q, r, the function checks if point q
    lies on line segment 'pr'."""
    if (q.x <= max(p.x, r.x)) and (q.x >= min(p.x, r.x)):
        if (q.y <= max(p.y, r.y)) and (q.y >= min(p.y, r.y)):
            return True
    return False


def edge_intersect(p1: Point, q1: Point, edge: Edge) -> bool:
    """Return True if edge from A, B interects edge.
    http://www.geeksforgeeks.org/check-if-two-given-line-segments-intersect/"""
    p2 = edge.p1
    q2 = edge.p2
    o1 = ccw(p1, q1, p2)
    o2 = ccw(p1, q1, q2)
    o3 = ccw(p2, q2, p1)
    o4 = ccw(p2, q2, q1)

    # General case
    if (o1 != o2 and o3 != o4):
        return True
    # p1, q1 and p2 are colinear and p2 lies on segment p1q1
    if o1 == COLLINEAR and on_segment(p1, p2, q1):
        return True
    # p1, q1 and p2 are colinear and q2 lies on segment p1q1
    if o2 == COLLINEAR and on_segment(p1, q2, q1):
        return True
    # p2, q2 and p1 are colinear and p1 lies on segment p2q2
    if o3 == COLLINEAR and on_segment(p2, p1, q2):
        return True
    # p2, q2 and q1 are colinear and q1 lies on segment p2q2
    if o4 == COLLINEAR and on_segment(p2, q1, q2):
        return True
    return False


class OpenEdges:
    def __init__(self) -> None:
        self._open_edges: list[Edge] = []

    def insert(self, p1: Point, p2: Point, edge: Edge) -> None:
        self._open_edges.insert(self._index(p1, p2, edge), edge)

    def delete(self, p1: Point, p2: Point, edge: Edge) -> None:
        index = self._index(p1, p2, edge) - 1
        if self._open_edges[index] == edge:
            del self._open_edges[index]

    def smallest(self) -> Edge:
        return self._open_edges[0]

    def _less_than(self, p1: Point, p2: Point, edge1: Edge,
                   edge2: Edge) -> bool:
        """Return True if edge1 is smaller than edge2, False otherwise."""
        if edge1 == edge2:
            return False
        if not edge_intersect(p1, p2, edge2):
            return True
        edge1_dist = point_edge_distance(p1, p2, edge1)
        edge2_dist = point_edge_distance(p1, p2, edge2)
        if edge1_dist > edge2_dist:
            return False
        if edge1_dist < edge2_dist:
            return True
        # The distance is equal, so compare on the edge angles.
        if edge1.p1 in edge2:
            same_point = edge1.p1
        else:
            same_point = edge1.p2
        angle_edge1 = angle2(p1, p2, edge1.get_adjacent(same_point))
        angle_edge2 = angle2(p1, p2, edge2.get_adjacent(same_point))
        if angle_edge1 < angle_edge2:
            return True
        return False

    def _index(self, p1: Point, p2: Point, edge: Edge) -> int:
        lo = 0
        hi = len(self._open_edges)
        while lo < hi:
            mid = (lo+hi)//2
            if self._less_than(p1, p2, edge, self._open_edges[mid]):
                hi = mid
            else:
                lo = mid + 1
        return lo

    def __len__(self) -> int:
        return len(self._open_edges)

    def __getitem__(self, index: int) -> Edge:
        return self._open_edges[index]
