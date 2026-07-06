"""Load polygons from any geopandas-supported file into pyvisgraph format.

This module must stay free of Qt imports so it can be unit tested headless.
Coordinates are treated as planar; geographic files (e.g. KML in EPSG:4326)
are not reprojected, which is fine for small extents since pyvisgraph's
math is Euclidean anyway.
"""
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

import geopandas as gpd
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.validation import make_valid

from pyvisgraph.graph import Point

BOUNDARY_NAME = 'boundary'
# The exclusion frame is the map bounds grown by this fraction of the larger
# extent, so it strictly contains the boundary. Its interior-minus-navigable is
# the off-limits solid; the four frame corners are the only extra vertices.
FRAME_MARGIN_FRAC = 0.05


@dataclass
class LoadResult:
    polygons: List[List[Point]]  # dissolved, for building the visgraph
    raw_polygons: List[List[Point]]  # as read from the file, for display;
    # rings oriented for winding fill (exteriors CCW, holes CW)
    bounds: Tuple[float, float, float, float]  # minx, miny, maxx, maxy
    skipped: int  # non-polygonal geometries that were ignored
    boundary: Optional[List[List[Point]]] = None  # exclusion-zone boundary
    # rings (oriented, exterior CCW / holes CW), or None when the map has no
    # outer boundary. When set, `polygons` describes the off-limits solid
    # (everything outside the boundary, plus obstacles) instead of the
    # obstacles themselves.


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


def _valid_parts(geom: BaseGeometry) -> List[Polygon]:
    """Return the Polygon parts of geom, repairing invalid rings.

    make_valid splits a self-intersecting (bowtie) ring into its lobes.
    """
    parts = []
    for poly in _polygonal_parts(geom):
        if poly.is_valid:
            parts.append(poly)
        else:
            parts.extend(_polygonal_parts(make_valid(poly)))
    return parts


def _rings_of(geom: BaseGeometry) -> List[List[Point]]:
    """Return oriented rings (exterior CCW, holes CW) for every polygon in
    geom, as pyvisgraph point lists. Degenerate rings are dropped."""
    rings = []
    for poly in _polygonal_parts(geom):
        oriented = orient(poly)
        for ring in [oriented.exterior] + list(oriented.interiors):
            points = _ring_to_points(ring.coords)
            if points is not None:
                rings.append(points)
    return rings


def _exclusion_polygons(
        obstacle_parts: List[Polygon], boundary_geom: BaseGeometry,
        bounds: Tuple[float, float, float, float]) -> BaseGeometry:
    """Return the off-limits solid: everything inside a bounding frame that is
    not navigable, where navigable = inside the boundary minus the obstacles.

    Fed through pyvisgraph's even-odd solidness rule this inverts the map:
    outside the boundary is solid, the navigable interior is free, and
    obstacles (including ones straddling the boundary) stay solid. Obstacles
    that cross the boundary are resolved by the shapely booleans, so the rings
    handed to the sweep never cross.
    """
    obstacles = unary_union(obstacle_parts) if obstacle_parts else None
    if obstacles is not None and not obstacles.is_empty:
        navigable = boundary_geom.difference(obstacles)
    else:
        navigable = boundary_geom
    minx, miny, maxx, maxy = bounds
    margin = FRAME_MARGIN_FRAC * max(maxx - minx, maxy - miny, 1e-9)
    frame = box(minx - margin, miny - margin, maxx + margin, maxy + margin)
    return frame.difference(navigable)


def load_polygons(path: str, layer: Optional[str] = None,
                  boundary_name: str = BOUNDARY_NAME) -> LoadResult:
    """Read a geopandas-supported file and return pyvisgraph polygons.

    MultiPolygons are exploded into individual polygons. Invalid polygons
    (e.g. self-intersecting rings) are repaired with make_valid, which
    splits a bowtie into its lobes. Overlapping or touching polygons are
    dissolved into their union, since pyvisgraph's rotational sweep assumes
    polygon edges never cross; raw_polygons keeps the (repaired) shapes so
    they can still be displayed individually. Interior rings (holes) become
    additional obstacle polygons. Non-polygonal geometries are skipped and
    counted in LoadResult.skipped.

    A feature whose Name equals boundary_name (case-insensitive) is treated as
    the outer navigable boundary: the returned polygons then describe the
    off-limits solid outside it (see _exclusion_polygons) and LoadResult.
    boundary holds the boundary rings for display. Files without such a
    feature behave exactly as before (boundary is None).
    """
    if layer is not None:
        gdf = gpd.read_file(path, layer=layer)
    else:
        gdf = gpd.read_file(path)

    names = (gdf['Name'] if 'Name' in gdf.columns
             else [None] * len(gdf.geometry))
    marker = boundary_name.strip().lower()

    obstacle_parts: List[Polygon] = []
    boundary_parts: List[Polygon] = []
    skipped = 0
    for name, geom in zip(names, gdf.geometry):
        if geom is None:
            skipped += 1
            continue
        feature_parts = _valid_parts(geom)
        if not feature_parts:
            skipped += 1
            continue
        is_boundary = (name is not None
                       and str(name).strip().lower() == marker)
        (boundary_parts if is_boundary else obstacle_parts).extend(
            feature_parts)

    # Exteriors CCW and holes CW so a winding fill paints overlap regions
    # solid while keeping holes empty.
    raw_polygons = []
    for poly in obstacle_parts:
        raw_polygons.extend(_rings_of(poly))

    boundary: Optional[List[List[Point]]] = None
    if boundary_parts:
        boundary_geom = unary_union(boundary_parts)
        off_limits = _exclusion_polygons(
            obstacle_parts, boundary_geom, tuple(gdf.total_bounds))
        polygons = _rings_of(off_limits)
        boundary = _rings_of(boundary_geom)
    else:
        merged = unary_union(obstacle_parts) if obstacle_parts else None
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
                      bounds=(minx, miny, maxx, maxy), skipped=skipped,
                      boundary=boundary)
