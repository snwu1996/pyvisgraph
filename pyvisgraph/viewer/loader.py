"""Load polygons from any geopandas-supported file into pyvisgraph format.

This module must stay free of Qt imports so it can be unit tested headless.
Coordinates are treated as planar; geographic files (e.g. KML in EPSG:4326)
are not reprojected, which is fine for small extents since pyvisgraph's
math is Euclidean anyway.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

import geopandas as gpd

from pyvisgraph.graph import Point


@dataclass
class LoadResult:
    polygons: List[List[Point]]
    bounds: Tuple[float, float, float, float]  # minx, miny, maxx, maxy
    skipped: int  # non-polygonal geometries that were ignored


def _ring_to_points(coords) -> Optional[List[Point]]:
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


def load_polygons(path: str, layer: Optional[str] = None) -> LoadResult:
    """Read a geopandas-supported file and return pyvisgraph polygons.

    MultiPolygons are exploded into individual polygons. Interior rings
    (holes) become additional obstacle polygons. Non-polygonal geometries
    are skipped and counted in LoadResult.skipped.
    """
    if layer is not None:
        gdf = gpd.read_file(path, layer=layer)
    else:
        gdf = gpd.read_file(path)

    polygons = []
    skipped = 0
    for geom in gdf.geometry:
        if geom is None:
            skipped += 1
            continue
        if geom.geom_type == 'Polygon':
            parts = [geom]
        elif geom.geom_type == 'MultiPolygon':
            parts = list(geom.geoms)
        else:
            skipped += 1
            continue
        for poly in parts:
            for ring in [poly.exterior] + list(poly.interiors):
                points = _ring_to_points(ring.coords)
                if points is not None:
                    polygons.append(points)

    if not polygons:
        raise ValueError('No polygons found in {}'.format(path))
    minx, miny, maxx, maxy = gdf.total_bounds
    return LoadResult(polygons=polygons, bounds=(minx, miny, maxx, maxy),
                      skipped=skipped)
