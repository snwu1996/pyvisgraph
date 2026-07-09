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
    # Thin wrapper over the core helper so the tests below read the same.
    return vg.path_length(path)


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


class TestBoundaryZoneBuild:
    """The same exclusion-zone map as TestBoundaryInversion, but built through
    the native ``VisGraph.build(input, boundary=...)`` API instead of hand-
    assembling the frame. The boundary zone logic now lives in the core
    library, so passing obstacles + a navigable boundary must reproduce the
    inverted map."""

    BOUNDARY = [rect(0, 0, 10, 10)]    # navigable region (a list of rings)
    OBSTACLES = [rect(4, 4, 6, 6)]     # an island inside it

    def _build(self):
        graph = vg.VisGraph()
        graph.build(self.OBSTACLES, boundary=self.BOUNDARY, status=False)
        return graph

    def test_boundary_inverts_solidness(self):
        graph = self._build()
        # Just outside the boundary (x=0) but inside the tight auto-frame.
        assert graph.point_in_solid(vg.Point(-0.2, 5))
        assert not graph.point_in_solid(vg.Point(1, 5))  # navigable interior
        assert graph.point_in_solid(vg.Point(5, 5))      # obstacle island
        assert graph.boundary is self.BOUNDARY

    def test_frame_encloses_the_boundary(self):
        # The auto-added frame sits FRAME_MARGIN_FRAC outside the extent, so a
        # point just beyond the boundary is off-limits, not off the map.
        graph = self._build()
        assert graph.point_in_solid(vg.Point(-0.4 * 10 * vg.FRAME_MARGIN_FRAC,
                                             5))

    def test_path_routes_around_obstacle_inside_boundary(self):
        graph = self._build()
        left, right = vg.Point(1, 5), vg.Point(9, 5)
        path = graph.shortest_path(left, right)
        assert path[0] == left and path[-1] == right
        straight = math.hypot(right.x - left.x, right.y - left.y)
        assert path_length(path) > straight  # detoured around the island

    def test_cannot_leave_the_boundary(self):
        # Everything outside the boundary is solid, so a navigable point cannot
        # reach a point out in the off-limits region.
        graph = self._build()
        assert graph.shortest_path(vg.Point(1, 5), vg.Point(-0.2, 5)) == []

    def test_no_boundary_builds_ordinary_map(self):
        # Without a boundary the obstacle is just an obstacle: its interior is
        # solid but the surrounding world is free and unbounded.
        graph = vg.VisGraph()
        graph.build(self.OBSTACLES, status=False)
        assert graph.boundary is None
        assert graph.point_in_solid(vg.Point(5, 5))
        assert not graph.point_in_solid(vg.Point(-2, 5))  # free, not off-limits


class TestInvertBoundaryHelper:
    """The shapely-free frame inversion, exercised directly. This is what the
    vgstudio loader delegates to after computing its navigable region."""

    def test_prepends_frame_and_keeps_rings(self):
        boundary = [rect(0, 0, 10, 10)]
        obstacles = [rect(4, 4, 6, 6)]
        rings = vg.invert_boundary(obstacles, boundary)
        # frame + 1 boundary ring + 1 obstacle ring
        assert len(rings) == 3
        # The frame strictly contains the [0,10] extent on every side.
        frame_xs = [p.x for p in rings[0]]
        frame_ys = [p.y for p in rings[0]]
        assert min(frame_xs) < 0 and max(frame_xs) > 10
        assert min(frame_ys) < 0 and max(frame_ys) > 10

    def test_does_not_mutate_caller_rings(self):
        boundary = [rect(0, 0, 10, 10)]
        obstacles = [rect(4, 4, 6, 6)]
        before = [list(r) for r in boundary + obstacles]
        vg.invert_boundary(obstacles, boundary)
        # Graph pops the closing point off its rings; invert_boundary copies so
        # the originals are untouched.
        assert [boundary[0], obstacles[0]] == before

    def test_explicit_bounds_override_extent(self):
        boundary = [rect(0, 0, 10, 10)]
        # A frame sized to a far larger extent puts its corners well past 10.
        rings = vg.invert_boundary([], boundary, bounds=(-100, -100, 100, 100))
        assert min(p.x for p in rings[0]) < -100


class TestNearCollinearSweep:
    """Buffered/dissolved geometry (shapely mitre joins) produces several ring
    vertices along one straight line whose angles from each other differ only
    by float noise. The rotational sweep must still scan such same-ray points
    near to far, or its collinear occlusion logic is bypassed and visibility
    edges cut through solid space. These rings are the exact output of
    buffering a real map (obstacle buffer 5, boundary buffer 10) where three
    obstacles merged into the exclusion zone; A, N, C and B below lie on one
    grown obstacle edge line, with a solid lobe between N and C."""

    FRAME = [vg.Point(-196.04142204827136, -82.87046873543937),
             vg.Point(288.5013512254217, -82.87046873543937),
             vg.Point(288.5013512254217, 162.01616811108005),
             vg.Point(-196.04142204827136, 162.01616811108005)]
    NAVIGABLE = [vg.Point(-142.18572470143152, 103.47323301178456),
                 vg.Point(-157.850083828513, -26.773012322651912),
                 vg.Point(69.84314148261413, -45.806192147421044),
                 vg.Point(243.4064260875464, -29.326445932407275),
                 vg.Point(250.96818779123717, 124.86773837328697),
                 vg.Point(-103.14341426600883, 120.7204853762201),
                 vg.Point(-83.29217648830809, 115.36928214918773),
                 vg.Point(-78.8163402871447, 117.35143818113151),
                 vg.Point(-76.44989147515085, 113.52484010216273),
                 vg.Point(-73.16363038521183, 112.63897841704873),
                 vg.Point(-73.18288498338242, 112.35478663886018),
                 vg.Point(-75.53877952187852, 112.05155268836067),
                 vg.Point(-54.04224841789887, 77.29120452022337),
                 vg.Point(119.58061436041926, 98.2189603015385),
                 vg.Point(190.66739043055574, 32.935186359576456),
                 vg.Point(35.183292005042254, -13.956843324308554),
                 vg.Point(-74.99753051624795, 19.50548055252773),
                 vg.Point(-59.38511434772077, 74.00700608629538),
                 vg.Point(-121.5255228705173, 67.35729447315481),
                 vg.Point(-131.52064721725768, 94.01095939779576),
                 vg.Point(-97.03010468619107, 109.2853425186967)]
    POCKET = [vg.Point(-140.1635891369843, 120.28691576061408),
              vg.Point(-140.84032399580423, 114.65999073079666),
              vg.Point(-132.1078570587093, 120.38126217234162)]

    # Same ray from A (ccw-collinear within COLIN_TOLERANCE): its ring
    # neighbour N, then C and B across the solid lobe.
    A = vg.Point(-131.52064721725768, 94.01095939779576)
    N = vg.Point(-97.03010468619107, 109.2853425186967)
    C = vg.Point(-83.29217648830809, 115.36928214918773)
    B = vg.Point(-78.8163402871447, 117.35143818113151)

    def _build(self):
        return build([self.FRAME, self.NAVIGABLE, self.POCKET])

    def test_lobe_between_the_collinear_points_is_solid(self):
        graph = self._build()
        mid = vg.Point((self.N.x + self.C.x) / 2, (self.N.y + self.C.y) / 2)
        assert graph.point_in_solid(mid)

    def test_no_visibility_edge_through_the_lobe(self):
        graph = self._build()
        visible = {edge.get_adjacent(self.A)
                   for edge in graph.visgraph[self.A]}
        # The nearer collinear point is A's ring neighbour and stays visible;
        # the two beyond the solid lobe must be occluded.
        assert self.N in visible
        assert self.C not in visible
        assert self.B not in visible


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
