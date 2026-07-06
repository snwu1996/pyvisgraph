"""Graphics scene holding the obstacle map, visibility graph and path layers."""
from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import QObject, QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem,
                             QGraphicsPathItem, QGraphicsScene)

import pyvisgraph as vg

VIS_EDGE_COLOR = QColor('#d3d3d3')
POLYGON_EDGE_COLOR = QColor('#000000')
POLYGON_FILL_COLOR = QColor('#f2f2f2')
PATH_COLOR = QColor('#ff0000')
START_COLOR = QColor('#00a000')
END_COLOR = QColor('#8b0000')

BACKGROUND_COLOR = QColor('#ffffff')
# When a map has an exclusion boundary the whole world is off-limits except
# the navigable interior: the background becomes off-limits gray, the interior
# is painted white, and the boundary is outlined.
OFF_LIMITS_COLOR = QColor('#d9d9d9')
NAVIGABLE_COLOR = QColor('#ffffff')
BOUNDARY_COLOR = QColor('#1565c0')

MARKER_RADIUS = 5  # pixels; markers ignore view transforms


def _cosmetic_pen(color: QColor, width: float):
    pen = QPen(color, width)
    pen.setCosmetic(True)
    return pen


def _marker(color: QColor):
    # Centered on its position and unaffected by zoom or the view's y-flip.
    item = QGraphicsEllipseItem(-MARKER_RADIUS, -MARKER_RADIUS,
                                2 * MARKER_RADIUS, 2 * MARKER_RADIUS)
    item.setBrush(QBrush(color))
    item.setPen(_cosmetic_pen(color.darker(130), 1))
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    return item


class VisGraphScene(QGraphicsScene):
    """Layers, bottom to top: visibility edges, polygons, path, markers.

    Thousands of visibility edges are batched into a single QGraphicsPathItem
    so the scene stays responsive on dense graphs.
    """

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(BACKGROUND_COLOR))

        # Navigable interior, painted white over the off-limits background;
        # sits below the visibility edges so they draw on top of it.
        self.navigable_item = QGraphicsPathItem()
        self.navigable_item.setPen(QPen(Qt.PenStyle.NoPen))
        self.navigable_item.setBrush(QBrush(NAVIGABLE_COLOR))
        self.navigable_item.setZValue(-1)

        self.vis_edges_item = QGraphicsPathItem()
        self.vis_edges_item.setPen(_cosmetic_pen(VIS_EDGE_COLOR, 1))
        self.vis_edges_item.setZValue(0)

        self.polygons_item = QGraphicsPathItem()
        self.polygons_item.setPen(_cosmetic_pen(POLYGON_EDGE_COLOR, 1.5))
        self.polygons_item.setBrush(QBrush(POLYGON_FILL_COLOR))
        self.polygons_item.setZValue(1)

        # Exclusion-zone outline, above the obstacle fill.
        self.boundary_item = QGraphicsPathItem()
        boundary_pen = _cosmetic_pen(BOUNDARY_COLOR, 2)
        boundary_pen.setStyle(Qt.PenStyle.DashLine)
        self.boundary_item.setPen(boundary_pen)
        self.boundary_item.setZValue(1.5)

        self.path_item = QGraphicsPathItem()
        self.path_item.setPen(_cosmetic_pen(PATH_COLOR, 2.5))
        self.path_item.setZValue(2)

        self.start_item = _marker(START_COLOR)
        self.start_item.setZValue(3)
        self.start_item.setVisible(False)

        self.end_item = _marker(END_COLOR)
        self.end_item.setZValue(3)
        self.end_item.setVisible(False)

        for item in (self.navigable_item, self.vis_edges_item,
                     self.polygons_item, self.boundary_item, self.path_item,
                     self.start_item, self.end_item):
            self.addItem(item)

    def set_polygons(self, polygons: list[list[vg.Point]]):
        """polygons: list of list of vg.Point (open rings).

        Rings must be oriented as the loader emits them (exteriors CCW,
        holes CW): the winding fill then paints overlapping obstacles
        solid while leaving holes empty.
        """
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        for polygon in polygons:
            path.addPolygon(QPolygonF([QPointF(p.x, p.y) for p in polygon]))
            path.closeSubpath()
        self.polygons_item.setPath(path)

    def set_boundary(self, rings: list[list[vg.Point]] | None):
        """Show (or clear) the exclusion-zone boundary.

        rings: the boundary polygon rings (as the loader emits them), or None
        for a map without a boundary. With a boundary the whole scene is
        off-limits gray except the navigable interior, which is painted white
        and outlined; without one the scene reverts to a plain white
        background with obstacles filled gray.
        """
        if not rings:
            self.setBackgroundBrush(QBrush(BACKGROUND_COLOR))
            self.navigable_item.setPath(QPainterPath())
            self.boundary_item.setPath(QPainterPath())
            self.polygons_item.setBrush(QBrush(POLYGON_FILL_COLOR))
            return
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        for ring in rings:
            path.addPolygon(QPolygonF([QPointF(p.x, p.y) for p in ring]))
            path.closeSubpath()
        self.setBackgroundBrush(QBrush(OFF_LIMITS_COLOR))
        self.navigable_item.setPath(path)
        self.boundary_item.setPath(path)
        self.polygons_item.setBrush(QBrush(OFF_LIMITS_COLOR))

    def set_vis_edges(self, edges: Iterable[vg.Edge]):
        """edges: iterable of vg.Edge."""
        path = QPainterPath()
        for edge in edges:
            path.moveTo(edge.p1.x, edge.p1.y)
            path.lineTo(edge.p2.x, edge.p2.y)
        self.vis_edges_item.setPath(path)

    def set_vis_edges_visible(self, visible: bool):
        self.vis_edges_item.setVisible(visible)

    def set_path(self, points: list[vg.Point] | None):
        """points: in-order list of vg.Point, or None to clear."""
        path = QPainterPath()
        if points:
            path.moveTo(points[0].x, points[0].y)
            for p in points[1:]:
                path.lineTo(p.x, p.y)
        self.path_item.setPath(path)

    def set_start(self, point: vg.Point | None):
        self._place_marker(self.start_item, point)

    def set_end(self, point: vg.Point | None):
        self._place_marker(self.end_item, point)

    @staticmethod
    def _place_marker(item: QGraphicsEllipseItem, point: vg.Point | None):
        if point is None:
            item.setVisible(False)
        else:
            item.setPos(point.x, point.y)
            item.setVisible(True)
