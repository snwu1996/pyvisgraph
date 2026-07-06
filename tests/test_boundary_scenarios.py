"""Core-library coverage for the even-odd solidness, boundary-inversion and
concave-detour behaviours that used to be exercised only through the viewer's
KML loader (tests/test_viewer_loader.py, now in the separate visgraph-studio
repo).

Everything here is built from in-memory polygons, so the suite stays free of
geopandas/shapely/KML. Each entry in the polygon list passed to
``VisGraph.build`` is one ring / one polygon id; solidness follows the even-odd
rule across all of them (see pyvisgraph/visible_vertices.py::point_in_solid),
which is exactly how the loader represents donut holes and inverted
exclusion-zone boundaries.
"""
import math

import pyvisgraph as vg


def build(polygons):
    graph = vg.VisGraph()
    graph.build(polygons, status=False)
    return graph


def rect(x0, y0, x1, y1):
    """Open, counter-clockwise rectangle ring."""
    return [vg.Point(x0, y0), vg.Point(x1, y0),
            vg.Point(x1, y1), vg.Point(x0, y1)]


def path_length(path):
    return sum(math.hypot(p2.x - p1.x, p2.y - p1.y)
               for p1, p2 in zip(path, path[1:]))


class TestEvenOddDonut:
    """A square obstacle with a nested hole ring: the courtyard is interior to
    two polygons, so the even-odd rule makes it free space (the donut contract
    from CLAUDE.md)."""

    # Outer wall 0..10, square hole 3..7. Two rings => two polygon ids.
    POLYGONS = [rect(0, 0, 10, 10), rect(3, 3, 7, 7)]

    def test_wall_is_solid_hole_and_outside_are_free(self):
        graph = build(self.POLYGONS)
        assert graph.point_in_solid(vg.Point(1, 5))    # in the wall
        assert not graph.point_in_solid(vg.Point(5, 5))  # in the hole
        assert not graph.point_in_solid(vg.Point(15, 5))  # outside entirely

    def test_two_points_inside_hole_are_connected(self):
        graph = build(self.POLYGONS)
        path = graph.shortest_path(vg.Point(4, 5), vg.Point(6, 5))
        assert len(path) >= 2
        assert path[0] == vg.Point(4, 5)
        assert path[-1] == vg.Point(6, 5)

    def test_hole_is_sealed_off_from_outside(self):
        # The wall fully encloses the courtyard, so there is no way out.
        graph = build(self.POLYGONS)
        assert graph.shortest_path(vg.Point(5, 5), vg.Point(15, 5)) == []


class TestBoundaryInversion:
    """Replicates the loader's off_limits = frame - (boundary - obstacles):
    a big frame ring, the navigable boundary punched out of it as a hole, and
    an obstacle island re-solidified inside. Represented as a flat list of
    rings resolved by the even-odd rule -- no shapely needed."""

    #   frame   -5..15  (solid by itself)
    #   boundary 0..10  (navigable hole inside the frame)
    #   obstacle 4..6   (island back to solid inside the navigable area)
    POLYGONS = [rect(-5, -5, 15, 15), rect(0, 0, 10, 10), rect(4, 4, 6, 6)]

    def test_solidness_matches_exclusion_zone(self):
        graph = build(self.POLYGONS)
        # outside the boundary but inside the frame is off-limits (solid)
        assert graph.point_in_solid(vg.Point(-2, 5))
        # navigable interior is free
        assert not graph.point_in_solid(vg.Point(1, 5))
        # the obstacle island is solid again
        assert graph.point_in_solid(vg.Point(5, 5))

    def test_path_routes_around_obstacle(self):
        graph = build(self.POLYGONS)
        left, right = vg.Point(1, 5), vg.Point(9, 5)
        path = graph.shortest_path(left, right)
        assert len(path) >= 2
        assert path[0] == left and path[-1] == right
        # The straight line crosses the obstacle (x 4..6), so the detour must
        # be strictly longer and must swing clear of the obstacle band in y.
        straight = math.hypot(right.x - left.x, right.y - left.y)
        assert path_length(path) > straight
        # The detour hugs an obstacle corner (y = 4 or 6) off the y=5 line.
        assert max(p.y for p in path) >= 6 or min(p.y for p in path) <= 4


class TestConcaveDetour:
    """A solid peninsula hanging from the top forces a path between two points
    near its base to detour all the way around the tip (port of the loader's
    concave-boundary test at the core-library level)."""

    # Vertical wall x 4..6 hanging down to a tip at y=2, extending far above
    # the test points so routing over the top is the long way round.
    POLYGONS = [rect(4, 2, 6, 20)]

    def test_peninsula_solidness(self):
        graph = build(self.POLYGONS)
        assert graph.point_in_solid(vg.Point(5, 5))     # in the peninsula
        assert not graph.point_in_solid(vg.Point(5, 1))  # below its tip

    def test_path_detours_below_tip(self):
        graph = build(self.POLYGONS)
        left, right = vg.Point(2, 9), vg.Point(8, 9)
        path = graph.shortest_path(left, right)
        assert len(path) >= 2
        # Must dip below the tip (y=2) rather than cut across the wall, and so
        # be meaningfully longer than the blocked straight line.
        assert min(p.y for p in path) <= 2
        straight = math.hypot(right.x - left.x, right.y - left.y)
        assert path_length(path) > straight * 1.2
