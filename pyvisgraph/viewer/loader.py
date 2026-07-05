"""Load polygons from any geopandas-supported file into pyvisgraph format.

This module must stay free of Qt imports so it can be unit tested headless.
Coordinates are treated as planar; geographic files (e.g. KML in EPSG:4326)
are not reprojected, which is fine for small extents since pyvisgraph's
math is Euclidean anyway.
"""
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

import geopandas as gpd
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.validation import make_valid

from pyvisgraph.graph import Point


@dataclass
class LoadResult:
    polygons: List[List[Point]]  # dissolved, for building the visgraph
    raw_polygons: List[List[Point]]  # as read from the file, for display;
    # rings oriented for winding fill (exteriors CCW, holes CW)
    bounds: Tuple[float, float, float, float]  # minx, miny, maxx, maxy
    skipped: int  # non-polygonal geometries that were ignored


def _ring_to_points(coords: Iterable[Sequence[float]]) -> Optional[List[Point]]:
    """Convert a shapely ring coordinate sequence to a list of Points.

    Drops the duplicate closing coordinate and consecutive duplicates.
    Returns None for degenerate rings with fewer than 3 distinct points.
    """
    points = []
    for x, y, *_ in coords:
        if points and points[-1].x == x and points[-1].y == y:
            continue
        points.append(Point(x, y))
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        return None
    return points


def _polygonal_parts(geom: BaseGeometry) -> List[Polygon]:
    """Flatten a geometry into its Polygon parts, dropping anything else."""
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, (MultiPolygon, GeometryCollection)):
        parts = []
        for g in geom.geoms:
            parts.extend(_polygonal_parts(g))
        return parts
    return []


def load_polygons(path: str, layer: Optional[str] = None) -> LoadResult:
    """Read a geopandas-supported file and return pyvisgraph polygons.

    MultiPolygons are exploded into individual polygons. Invalid polygons
    (e.g. self-intersecting rings) are repaired with make_valid, which
    splits a bowtie into its lobes. Overlapping or touching polygons are
    dissolved into their union, since pyvisgraph's rotational sweep assumes
    polygon edges never cross; raw_polygons keeps the (repaired) shapes so
    they can still be displayed individually. Interior rings (holes) become
    additional obstacle polygons. Non-polygonal geometries are skipped and
    counted in LoadResult.skipped.
    """
    if layer is not None:
        gdf = gpd.read_file(path, layer=layer)
    else:
        gdf = gpd.read_file(path)

    parts = []
    skipped = 0
    for geom in gdf.geometry:
        if geom is None:
            skipped += 1
            continue
        feature_parts = _polygonal_parts(geom)
        if not feature_parts:
            skipped += 1
            continue
        for poly in feature_parts:
            if poly.is_valid:
                parts.append(poly)
            else:
                parts.extend(_polygonal_parts(make_valid(poly)))

    # Exteriors CCW and holes CW so a winding fill paints overlap regions
    # solid while keeping holes empty.
    raw_polygons = []
    for poly in parts:
        oriented = orient(poly)
        for ring in [oriented.exterior] + list(oriented.interiors):
            points = _ring_to_points(ring.coords)
            if points is not None:
                raw_polygons.append(points)

    merged = unary_union(parts) if parts else None
    if merged is None or merged.is_empty:
        parts = []
    elif isinstance(merged, Polygon):
        parts = [merged]
    else:
        assert isinstance(merged, MultiPolygon)  # union of polygons
        parts = list(merged.geoms)

    polygons = []
    for poly in parts:
        for ring in [poly.exterior] + list(poly.interiors):
            points = _ring_to_points(ring.coords)
            if points is not None:
                polygons.append(points)

    if not polygons:
        raise ValueError('No polygons found in {}'.format(path))
    minx, miny, maxx, maxy = gdf.total_bounds
    return LoadResult(polygons=polygons, raw_polygons=raw_polygons,
                      bounds=(minx, miny, maxx, maxy), skipped=skipped)
