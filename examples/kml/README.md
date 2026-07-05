# Example KML files

Obstacle maps of increasing complexity for `pyvisgraph-viewer`
(requires the `viewer` extras: `pip install pyvisgraph[viewer]`):

```
poetry run pyvisgraph-viewer examples/kml/simple.kml
poetry run pyvisgraph-viewer examples/kml/medium.kml
poetry run pyvisgraph-viewer examples/kml/complex.kml
poetry run pyvisgraph-viewer examples/kml/overlapping.kml
poetry run pyvisgraph-viewer examples/kml/nopath.kml
```

- **simple.kml** — three well-separated convex obstacles (rectangle, triangle, hexagon).
- **medium.kml** — concave L/U shapes, a star, a MultiGeometry placemark and a polygon with a hole.
- **complex.kml** — a maze of 20 staggered wall segments; paths must zig-zag through the gaps.
- **overlapping.kml** — two rectangles and a triangle that overlap each other;
  the original outlines are drawn, but paths route around their union.
- **nopath.kml** — four overlapping walls enclose a courtyard with no way in;
  two points inside the courtyard can reach each other, but no path exists
  between the courtyard and the outside.

In the viewer: click to set the start point (green), click again to set the
end point (dark red). The shortest path is drawn in red once both are set;
the next click starts a new pair. If either point lands inside an obstacle,
or the two points are separated by obstacles, the status bar reports that no
path exists. Obstacle interiors follow the even-odd rule, so the hole of a
donut-shaped obstacle is free space. Files can also be opened via File > Open.
