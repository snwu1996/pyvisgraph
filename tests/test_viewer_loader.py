"""Tests for the viewer's geopandas loader against the bundled example KMLs.

Skipped entirely if the optional 'viewer' extras are not installed.
"""
import glob
import math
import os

import pytest

pytest.importorskip("geopandas")

import pyvisgraph as vg
from pyvisgraph.viewer.loader import FRAME_MARGIN_FRAC, load_polygons

KML_DIR = os.path.join(os.path.dirname(__file__), '..', 'examples', 'kml')

# Every primary example map now carries a 'boundary' feature (see
# examples/kml/README.md); crossing.kml additionally has obstacles straddling
# and outside the boundary.
BOUNDARY_MAPS = ('simple.kml', 'medium.kml', 'complex.kml', 'overlapping.kml',
                 'nopath.kml', 'crossing.kml', 'concave.kml')


def kml(name):
    return os.path.join(KML_DIR, name)


def outside_boundary_point(result):
    """A point outside the boundary but inside the exclusion frame, i.e. in
    off-limits space, derived from the frame construction in the loader."""
    minx, miny, maxx, maxy = result.bounds
    margin = FRAME_MARGIN_FRAC * max(maxx - minx, maxy - miny)
    return vg.Point(minx - 0.4 * margin, (miny + maxy) / 2)


def benchmark_maps():
    return sorted(glob.glob(os.path.join(KML_DIR, 'benchmark',
                                         'map_*.kml')))


class TestLoadPolygons:

    def test_simple_polygon_count(self):
        result = load_polygons(kml('simple.kml'))
        assert result.boundary is not None
        assert len(result.raw_polygons) == 3  # 3 obstacles, boundary excluded
        # off-limits solid = frame with the navigable hole + 3 obstacle islands
        assert len(result.polygons) == 5
        assert result.skipped == 0

    def test_medium_explodes_multigeometry_and_holes(self):
        result = load_polygons(kml('medium.kml'))
        # 5 single polygons + 2 from MultiGeometry + outer and inner ring
        # of the square-with-hole = 9 obstacle rings (boundary excluded).
        assert len(result.raw_polygons) == 9

    def test_complex_polygon_count(self):
        result = load_polygons(kml('complex.kml'))
        assert len(result.raw_polygons) == 20

    def test_rings_are_open_and_clean(self):
        for name in ('simple.kml', 'medium.kml', 'complex.kml'):
            for polygon in load_polygons(kml(name)).polygons:
                assert len(polygon) >= 3
                assert polygon[0] != polygon[-1]
                for p1, p2 in zip(polygon, polygon[1:]):
                    assert p1 != p2

    def test_bounds(self):
        minx, miny, maxx, maxy = load_polygons(kml('simple.kml')).bounds
        assert minx < maxx
        assert miny < maxy
        # The boundary is now the outermost feature and sets the bounds.
        assert 6.0 <= minx and maxx <= 6.1
        assert 50.98 <= miny and maxy <= 51.07

    def test_overlapping_polygons_are_dissolved(self):
        # The three overlapping shapes must merge into a single obstacle,
        # since pyvisgraph's sweep assumes polygon edges never cross. The
        # raw shapes are kept as authored for display. Inside the boundary
        # they become one off-limits island (frame + navigable hole + island).
        result = load_polygons(kml('overlapping.kml'))
        assert len(result.raw_polygons) == 3
        assert len(result.polygons) == 3

    def test_nopath_walls_merge_into_ring_with_courtyard(self):
        # Four overlapping walls dissolve into one ring obstacle with a sealed
        # courtyard; with the boundary the off-limits solid is the frame plus
        # the navigable areas (outside the walls and the courtyard) as holes.
        result = load_polygons(kml('nopath.kml'))
        assert len(result.polygons) == 5
        assert len(result.raw_polygons) == 5  # 4 walls + triangle

    def test_no_boundary_when_marker_absent(self):
        # With a marker that matches nothing the map loads exactly as before
        # boundaries existed: no inversion, the 'boundary' rectangle is just
        # another (containing) obstacle that absorbs the shapes inside it.
        result = load_polygons(kml('simple.kml'), boundary_name='__none__')
        assert result.boundary is None
        assert len(result.raw_polygons) == 4  # 3 obstacles + the rectangle
        assert len(result.polygons) == 1  # dissolved into the rectangle

    def test_raw_ring_orientation(self):
        # Winding-fill display contract: exteriors CCW, holes CW.
        def signed_area(ring):
            return sum(p1.x * p2.y - p2.x * p1.y
                       for p1, p2 in zip(ring, ring[1:] + ring[:1])) / 2

        result = load_polygons(kml('medium.kml'))
        holes = [ring for ring in result.raw_polygons
                 if signed_area(ring) < 0]
        assert len(holes) == 1  # the square-with-hole's interior ring
        for name in ('simple.kml', 'overlapping.kml', 'nopath.kml'):
            for ring in load_polygons(kml(name)).raw_polygons:
                assert signed_area(ring) > 0

    def test_output_builds_visgraph_with_path(self):
        result = load_polygons(kml('simple.kml'))
        graph = vg.VisGraph()
        graph.build(result.polygons, status=False)
        path = graph.shortest_path(vg.Point(6.005, 51.005),
                                   vg.Point(6.095, 51.045))
        assert len(path) >= 2
        assert path[0] == vg.Point(6.005, 51.005)
        assert path[-1] == vg.Point(6.095, 51.045)


class TestExclusionBoundary:
    """A 'boundary' feature inverts the map: everything outside it is
    off-limits (solid) while the interior minus the obstacles is navigable."""

    @pytest.mark.parametrize('name', BOUNDARY_MAPS)
    def test_boundary_detected_and_map_inverted(self, name):
        result = load_polygons(kml(name))
        assert result.boundary  # not None and non-empty
        graph = vg.VisGraph()
        graph.build(result.polygons, status=False)
        # The whole point of an exclusion zone: outside the boundary is solid.
        assert graph.point_in_solid(outside_boundary_point(result))

    def test_crossing_merges_straddling_obstacles(self):
        # crossing.kml has obstacles straddling and outside the boundary; the
        # shapely booleans resolve the crossings into non-crossing rings.
        result = load_polygons(kml('crossing.kml'))
        assert result.boundary is not None
        graph = vg.VisGraph()
        graph.build(result.polygons, status=False)
        # straddle_left spans the left boundary edge (x=6.0).
        assert graph.point_in_solid(vg.Point(6.010, 51.015))  # inside part
        assert graph.point_in_solid(vg.Point(5.990, 51.015))  # outside part
        assert not graph.point_in_solid(vg.Point(6.090, 51.005))  # navigable
        # Two navigable points still route around the merged obstacles.
        path = graph.shortest_path(vg.Point(6.010, 51.045),
                                   vg.Point(6.090, 51.005))
        assert len(path) >= 2

    def test_concave_boundary_routes_around_peninsula(self):
        # concave.kml is a horseshoe: an off-limits peninsula drops from the
        # top between x 6.042 and 6.058 down to y 51.014. A path from the left
        # arm to the right arm must detour around the peninsula tip rather than
        # cut straight across it.
        result = load_polygons(kml('concave.kml'))
        graph = vg.VisGraph()
        graph.build(result.polygons, status=False)
        # A point in the middle of the peninsula is off-limits...
        assert graph.point_in_solid(vg.Point(6.050, 51.040))
        # ...while the passage below its tip is navigable.
        assert not graph.point_in_solid(vg.Point(6.050, 51.008))
        left, right = vg.Point(6.020, 51.045), vg.Point(6.080, 51.045)
        path = graph.shortest_path(left, right)
        assert len(path) >= 2
        # The detour dips below the peninsula tip and is longer than a straight
        # line, which would illegally cross the off-limits peninsula.
        assert min(p.y for p in path) <= 51.014
        straight = math.hypot(right.x - left.x, right.y - left.y)
        length = sum(math.hypot(p2.x - p1.x, p2.y - p1.y)
                     for p1, p2 in zip(path, path[1:]))
        assert length > straight * 1.2


class TestBenchmarkMaps:
    """The maps under examples/kml/benchmark/ feed
    examples/profile_shortest_path.py; some contain self-intersecting
    (bowtie) rings that the loader must repair rather than choke on."""

    @pytest.mark.parametrize('map_path', benchmark_maps(),
                             ids=os.path.basename)
    def test_benchmark_map_loads(self, map_path):
        result = load_polygons(map_path)
        assert result.polygons
        for polygon in result.polygons:
            assert len(polygon) >= 3
            assert polygon[0] != polygon[-1]

    def test_benchmark_maps_present(self):
        assert len(benchmark_maps()) == 30

    @pytest.mark.parametrize(
        'map_path', [m for m in benchmark_maps()
                     if 11 <= int(os.path.basename(m)[4:6]) <= 20],
        ids=os.path.basename)
    def test_overlap_benchmark_maps_dissolve(self, map_path):
        # Maps 11-20 draw obstacles as clusters of overlapping shapes;
        # dissolving must reduce the polygon count.
        result = load_polygons(map_path)
        assert len(result.polygons) < len(result.raw_polygons)

    @pytest.mark.parametrize(
        'map_path', [m for m in benchmark_maps()
                     if int(os.path.basename(m)[4:6]) >= 21],
        ids=os.path.basename)
    def test_holed_benchmark_maps_keep_holes(self, map_path):
        # Maps 21-30 place donut obstacles with 1-5 holes; the holes must
        # survive loading as clockwise rings in the display polygons.
        def signed_area(ring):
            return sum(p1.x * p2.y - p2.x * p1.y
                       for p1, p2 in zip(ring, ring[1:] + ring[:1])) / 2

        result = load_polygons(map_path)
        holes = sum(1 for ring in result.raw_polygons
                    if signed_area(ring) < 0)
        outers = len(result.raw_polygons) - holes
        assert holes >= outers  # every obstacle has at least one hole

    def test_smallest_benchmark_map_builds_and_routes(self):
        result = load_polygons(os.path.join(KML_DIR, 'benchmark',
                                            'map_01.kml'))
        g = vg.VisGraph()
        g.build(result.polygons, status=False)
        minx, miny, maxx, maxy = result.bounds
        origin = vg.Point(minx - 0.01, miny - 0.01)
        destination = vg.Point(maxx + 0.01, maxy + 0.01)
        path = g.shortest_path(origin, destination)
        assert len(path) >= 2
        assert path[0] == origin and path[-1] == destination
