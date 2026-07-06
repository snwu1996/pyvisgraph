"""Graphics view with map-style zoom/pan and click-to-place-point support."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter, QWheelEvent
from PyQt6.QtWidgets import (QApplication, QGraphicsScene, QGraphicsView,
                             QWidget)

ZOOM_FACTOR = 1.15
FIT_MARGIN = 0.05  # fraction of the bounds added on each side


class GraphView(QGraphicsView):
    """Left-drag pans, wheel zooms about the cursor.

    A press-release pair that moves less than the platform drag distance is
    treated as a click and emitted as pointClicked(x, y, button) in scene
    (world) coordinates. The view is y-flipped so map north is screen up.
    """

    pointClicked = pyqtSignal(float, float, Qt.MouseButton)

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.scale(1, -1)
        self._press_pos = None

    def wheelEvent(self, event: QWheelEvent | None):
        if event is None:
            return
        if event.angleDelta().y() > 0:
            factor = ZOOM_FACTOR
        else:
            # Don't let the user zoom out past the point where the whole
            # canvas (2x the polygon bounds) fits the viewport.
            min_scale = self._min_zoom_scale()
            current = abs(self.transform().m11())
            if current <= min_scale:
                return
            factor = max(1 / ZOOM_FACTOR, min_scale / current)
        self.scale(factor, factor)

    def _min_zoom_scale(self) -> float:
        """Scale at which the scene rect (the canvas) just fills the viewport."""
        rect = self.sceneRect()
        viewport = self.viewport()
        if rect.isEmpty() or viewport is None:
            return 0.0
        return min(viewport.width() / rect.width(),
                   viewport.height() / rect.height())

    def mousePressEvent(self, event: QMouseEvent | None):
        if event is not None:
            self._press_pos = event.position()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None):
        super().mouseReleaseEvent(event)
        if event is None or self._press_pos is None:
            return
        moved = (event.position() - self._press_pos).manhattanLength()
        self._press_pos = None
        if moved < QApplication.startDragDistance():
            scene_pos = self.mapToScene(event.position().toPoint())
            self.pointClicked.emit(scene_pos.x(), scene_pos.y(),
                                   event.button())

    def set_canvas(self, minx: float, miny: float,
                   maxx: float, maxy: float):
        """Fix the scrollable canvas to 2x the given bounds, centered on them.

        This caps how far out the user can zoom and pan: at minimum zoom the
        whole canvas fits the viewport, with the polygons centered in it.
        """
        width = (maxx - minx) or 1.0
        height = (maxy - miny) or 1.0
        cx = (minx + maxx) / 2
        cy = (miny + maxy) / 2
        self.setSceneRect(cx - width, cy - height, 2 * width, 2 * height)

    def fit_bounds(self, minx: float, miny: float,
                   maxx: float, maxy: float):
        margin_x = (maxx - minx) * FIT_MARGIN or 1.0
        margin_y = (maxy - miny) * FIT_MARGIN or 1.0
        rect = QRectF(QPointF(minx - margin_x, miny - margin_y),
                      QPointF(maxx + margin_x, maxy + margin_y))
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
