"""Tests for the viewer's geopandas loader against the bundled example KMLs.

Skipped entirely if the optional 'viewer' extras are not installed.
"""
import glob
import os

import pytest

pytest.importorskip("geopandas")

import pyvisgraph as vg
from pyvisgraph.viewer.loader import load_polygons

KML_DIR = os.path.join(os.path.dirname(__file__), '..', 'examples', 'kml')


def kml(name):
    return os.path.join(KML_DIR, name)


def benchmark_maps():
    return sorted(glob.glob(os.path.join(KML_DIR, 'benchmark',
                                         'map_*.kml')))


class TestLoadPolygons:

    def test_simple_polygon_count(self):
        result = load_polygons(kml('simple.kml'))
        assert len(result.polygons) == 3
        assert result.skipped == 0

    def test_medium_explodes_multigeometry_and_holes(self):
        result = load_polygons(kml('medium.kml'))
        # 5 single polygons + 2 from MultiGeometry + outer and inner ring
        # of the square-with-hole = 9 obstacle polygons.
        assert len(result.polygons) == 9

    def test_complex_polygon_count(self):
        result = load_polygons(kml('complex.kml'))
        assert len(result.polygons) == 20

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
        assert 6.0 <= minx and maxx <= 6.1
        assert 51.0 <= miny and maxy <= 51.06

    def test_overlapping_polygons_are_dissolved(self):
        # The three overlapping shapes must merge into a single obstacle,
        # since pyvisgraph's sweep assumes polygon edges never cross. The
        # raw shapes are kept as authored for display.
        result = load_polygons(kml('overlapping.kml'))
        assert len(result.polygons) == 1
        assert len(result.raw_polygons) == 3

    def test_nopath_walls_merge_into_ring_with_courtyard(self):
        # Four overlapping walls dissolve into one ring polygon whose
        # interior ring (the sealed courtyard) becomes a second polygon.
        result = load_polygons(kml('nopath.kml'))
        assert len(result.polygons) == 3  # ring + courtyard + triangle
        assert len(result.raw_polygons) == 5  # 4 walls + triangle

    def test_raw_polygons_match_dissolved_for_disjoint_maps(self):
        for name in ('simple.kml', 'complex.kml'):
            result = load_polygons(kml(name))
            assert len(result.raw_polygons) == len(result.polygons)

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
