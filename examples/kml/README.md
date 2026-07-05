# Example KML files

Obstacle maps of increasing complexity for `pyvisgraph-viewer`
(requires the `viewer` extras: `pip install pyvisgraph[viewer]`):

```
poetry run pyvisgraph-viewer examples/kml/simple.kml
poetry run pyvisgraph-viewer examples/kml/medium.kml
poetry run pyvisgraph-viewer examples/kml/complex.kml
```

- **simple.kml** — three well-separated convex obstacles (rectangle, triangle, hexagon).
- **medium.kml** — concave L/U shapes, a star, a MultiGeometry placemark and a polygon with a hole.
- **complex.kml** — a maze of 20 staggered wall segments; paths must zig-zag through the gaps.

In the viewer: click to set the start point (green), click again to set the
end point (dark red). The shortest path is drawn in red once both are set;
the next click starts a new pair. Files can also be opened via File > Open.
