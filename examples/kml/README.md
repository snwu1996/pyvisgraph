# Example KML files

Obstacle maps of increasing complexity for `pyvisgraph-viewer`
(requires the `viewer` extras: `pip install pyvisgraph[viewer]`):

```
poetry run pyvisgraph-viewer examples/kml/simple.kml
poetry run pyvisgraph-viewer examples/kml/medium.kml
poetry run pyvisgraph-viewer examples/kml/complex.kml
poetry run pyvisgraph-viewer examples/kml/overlapping.kml
poetry run pyvisgraph-viewer examples/kml/nopath.kml
poetry run pyvisgraph-viewer examples/kml/crossing.kml
poetry run pyvisgraph-viewer examples/kml/concave.kml
```

- **simple.kml** — three well-separated convex obstacles (rectangle, triangle, hexagon).
- **medium.kml** — concave L/U shapes, a star, a MultiGeometry placemark and a polygon with a hole.
- **complex.kml** — a maze of 20 staggered wall segments; paths must zig-zag through the gaps.
- **overlapping.kml** — two rectangles and a triangle that overlap each other;
  the original outlines are drawn, but paths route around their union.
- **nopath.kml** — four overlapping walls enclose a courtyard with no way in;
  two points inside the courtyard can reach each other, but no path exists
  between the courtyard and the outside.
- **crossing.kml** — an exclusion boundary that some obstacles straddle and one
  lies fully outside; the crossings are resolved so the boundary and obstacles
  never produce crossing edges.
- **concave.kml** — a horseshoe boundary: a deep off-limits peninsula drops
  from the top and splits the navigable area into two arms, so a path between
  them must detour all the way around the peninsula. (**simple.kml** also has a
  smaller such peninsula between its rectangle and triangle.)

## Exclusion boundaries

A placemark named **`boundary`** (case-insensitive) is treated as the outer
navigable boundary rather than an obstacle: everything **outside** it is
off-limits. In the viewer the off-limits area is shaded grey, the navigable
interior stays white, and the boundary is drawn as a dashed blue outline; a
start/end point placed outside the boundary is reported as off-limits, exactly
like one inside an obstacle. All the maps above carry such a boundary. An
obstacle may cross or sit outside the boundary — the loader unions and clips the
geometry so the sweep still sees only non-crossing rings. Use a different marker
with `--boundary NAME`, or omit the feature entirely to get the classic
obstacles-only behaviour.

The `benchmark/` folder holds 30 generated maps for
`examples/profile_shortest_path.py`; see `benchmark/benchmarks.md` for
per-map descriptions and the latest timing report.

In the viewer: click to set the start point (green), click again to set the
end point (dark red). The shortest path is drawn in red once both are set;
the next click starts a new pair. If either point lands inside an obstacle,
or the two points are separated by obstacles, the status bar reports that no
path exists. Obstacle interiors follow the even-odd rule, so the hole of a
donut-shaped obstacle is free space. Files can also be opened via File > Open.
