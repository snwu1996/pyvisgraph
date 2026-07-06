"""Generate 30 benchmark KML obstacle maps of increasing complexity.

Writes examples/kml/benchmark/map_01.kml ... map_30.kml. Maps 1-10 place
jittered n-gons on non-overlapping grid cells inside a small lon/lat
extent near the existing KML examples (6 E / 51 N). Maps 11-20 repeat the
same complexity ladder but group the shapes into clusters of 2-3 that
overlap each other, exercising the viewer loader's dissolve step. Maps
21-30 place donut-like obstacles with 1-5 holes each, exercising the
even-odd handling of interior rings. Deterministic: a fixed seed per map
makes the files reproducible fixtures for
examples/profile_shortest_path.py.
"""
import math
import os
import random

OUT_DIR = os.path.join(os.path.dirname(__file__), 'kml', 'benchmark')

# (polygon count) per map; vertex counts per polygon are drawn from 4-8.
POLYGON_COUNTS = [3, 6, 12, 20, 30, 45, 60, 80, 105, 130]

# (obstacle count) per holed map: each obstacle carries 1-5 holes, so it
# brings far more vertices than a plain polygon; a lower ladder keeps the
# biggest holed map comparable to map_10/map_20 in graph size.
HOLED_POLYGON_COUNTS = [2, 4, 7, 10, 14, 18, 23, 28, 34, 40]

# Map extent (degrees). Small enough that planar math is a fine approximation.
MIN_X, MIN_Y = 6.0, 51.0
WIDTH, HEIGHT = 0.5, 0.5

KML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{name}</name>
{placemarks}  </Document>
</kml>
"""

PLACEMARK_TEMPLATE = """    <Placemark>
      <name>obstacle_{i}</name>
      <Polygon>
        <outerBoundaryIs><LinearRing><coordinates>
          {coords}
        </coordinates></LinearRing></outerBoundaryIs>
{inner}      </Polygon>
    </Placemark>
"""

INNER_RING_TEMPLATE = """        <innerBoundaryIs><LinearRing><coordinates>
          {coords}
        </coordinates></LinearRing></innerBoundaryIs>
"""


def make_polygon(cx, cy, radius, sides, rng):
    """Convex polygon: jittered radii/angles around a center, sorted by angle."""
    angles = sorted(rng.uniform(0, 2 * math.pi) for _ in range(sides))
    points = []
    for a in angles:
        r = radius * rng.uniform(0.6, 1.0)
        points.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return points


def make_map(n_polygons, rng):
    """Place polygons in distinct cells of a grid covering the extent."""
    grid = math.ceil(math.sqrt(n_polygons * 1.3))
    cell_w, cell_h = WIDTH / grid, HEIGHT / grid
    cells = rng.sample([(i, j) for i in range(grid) for j in range(grid)],
                       n_polygons)
    polygons = []
    for i, j in cells:
        cx = MIN_X + (i + rng.uniform(0.35, 0.65)) * cell_w
        cy = MIN_Y + (j + rng.uniform(0.35, 0.65)) * cell_h
        radius = 0.3 * min(cell_w, cell_h)
        polygons.append(make_polygon(cx, cy, radius, rng.randint(4, 8), rng))
    return polygons


def make_overlapping_map(n_polygons, rng):
    """Group n_polygons shapes into clusters of 2-3 overlapping shapes.

    Each cluster gets its own grid cell (clusters never touch each other);
    within a cluster the shapes share a center up to a small offset, so
    they overlap and the loader has to dissolve them.
    """
    cluster_sizes = []
    remaining = n_polygons
    while remaining > 0:
        size = min(remaining, rng.randint(2, 3))
        cluster_sizes.append(size)
        remaining -= size
    grid = math.ceil(math.sqrt(len(cluster_sizes) * 1.3))
    cell_w, cell_h = WIDTH / grid, HEIGHT / grid
    cells = rng.sample([(i, j) for i in range(grid) for j in range(grid)],
                       len(cluster_sizes))
    radius = 0.2 * min(cell_w, cell_h)
    polygons = []
    for (i, j), size in zip(cells, cluster_sizes):
        cx = MIN_X + (i + rng.uniform(0.4, 0.6)) * cell_w
        cy = MIN_Y + (j + rng.uniform(0.4, 0.6)) * cell_h
        centers = [(cx, cy)]
        for _ in range(size - 1):
            a = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(0.2, 0.5) * radius
            centers.append((cx + d * math.cos(a), cy + d * math.sin(a)))
        for px, py in centers:
            polygons.append(
                make_polygon(px, py, radius, rng.randint(4, 8), rng))
    return polygons


def make_regular_polygon(cx, cy, radius, sides, rng):
    """N-gon with evenly spaced, lightly jittered angles and radii in
    [0.8, 1.0]*radius. Unlike make_polygon it is guaranteed to contain the
    disk of ~0.6*radius around its center, so holes placed there stay
    strictly inside."""
    base = rng.uniform(0, 2 * math.pi)
    step = 2 * math.pi / sides
    points = []
    for k in range(sides):
        a = base + (k + rng.uniform(-0.15, 0.15)) * step
        r = radius * rng.uniform(0.8, 1.0)
        points.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return points


def make_donut(cx, cy, radius, rng):
    """Obstacle with 1-5 holes: a regular-ish outer ring and mutually
    disjoint holes inside its guaranteed-interior disk."""
    outer = make_regular_polygon(cx, cy, radius, rng.randint(6, 10), rng)
    target = rng.randint(1, 5)
    placed = []  # (hx, hy, r) of accepted holes
    attempts = 0
    while len(placed) < target and attempts < 200:
        attempts += 1
        r = radius * rng.uniform(0.10, 0.20)
        d = rng.uniform(0, 0.55 * radius - r)
        a = rng.uniform(0, 2 * math.pi)
        hx, hy = cx + d * math.cos(a), cy + d * math.sin(a)
        if all(math.hypot(hx - px, hy - py) >= r + pr + 0.02 * radius
               for px, py, pr in placed):
            placed.append((hx, hy, r))
    # Holes wound opposite to the outer ring, as is conventional.
    holes = [make_regular_polygon(hx, hy, r, rng.randint(4, 6), rng)[::-1]
             for hx, hy, r in placed]
    return outer, holes


def make_donut_map(n_polygons, rng):
    """One donut obstacle per grid cell, like make_map but with holes."""
    grid = math.ceil(math.sqrt(n_polygons * 1.3))
    cell_w, cell_h = WIDTH / grid, HEIGHT / grid
    cells = rng.sample([(i, j) for i in range(grid) for j in range(grid)],
                       n_polygons)
    polygons = []
    for i, j in cells:
        cx = MIN_X + (i + rng.uniform(0.35, 0.65)) * cell_w
        cy = MIN_Y + (j + rng.uniform(0.35, 0.65)) * cell_h
        radius = 0.3 * min(cell_w, cell_h)
        polygons.append(make_donut(cx, cy, radius, rng))
    return polygons


def polygon_coords(points):
    ring = points + [points[0]]
    return ' '.join('{:.6f},{:.6f},0'.format(x, y) for x, y in ring)


def write_map(idx, n_polygons, polygons):
    """polygons: list of point lists, or of (outer, holes) tuples."""
    placemarks = []
    for i, polygon in enumerate(polygons):
        outer, holes = (polygon if isinstance(polygon, tuple)
                        else (polygon, []))
        inner = ''.join(INNER_RING_TEMPLATE.format(coords=polygon_coords(h))
                        for h in holes)
        placemarks.append(PLACEMARK_TEMPLATE.format(
            i=i, coords=polygon_coords(outer), inner=inner))
    name = 'pyvisgraph benchmark map {:02d} - {} obstacles'.format(
        idx, n_polygons)
    path = os.path.join(OUT_DIR, 'map_{:02d}.kml'.format(idx))
    with open(path, 'w') as f:
        f.write(KML_TEMPLATE.format(name=name,
                                    placemarks=''.join(placemarks)))
    print('wrote {} ({} obstacles)'.format(path, n_polygons))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for idx, n_polygons in enumerate(POLYGON_COUNTS, start=1):
        rng = random.Random(idx)
        write_map(idx, n_polygons, make_map(n_polygons, rng))
    for idx, n_polygons in enumerate(POLYGON_COUNTS, start=11):
        rng = random.Random(idx)
        write_map(idx, n_polygons, make_overlapping_map(n_polygons, rng))
    for idx, n_polygons in enumerate(HOLED_POLYGON_COUNTS, start=21):
        rng = random.Random(idx)
        write_map(idx, n_polygons, make_donut_map(n_polygons, rng))


if __name__ == '__main__':
    main()
