"""Main window wiring the loader, build worker, scene and interaction."""
import math
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow, QProgressBar

import pyvisgraph as vg

from pyvisgraph.viewer.loader import load_polygons
from pyvisgraph.viewer.scene import VisGraphScene
from pyvisgraph.viewer.view import GraphView
from pyvisgraph.viewer.worker import BuildWorker


class MainWindow(QMainWindow):

    def __init__(self, path, workers=1, layer=None):
        super().__init__()
        self.setWindowTitle('pyvisgraph viewer - {}'.format(
            os.path.basename(path)))
        self.resize(1000, 750)

        self.visgraph = None
        self.start = None
        self.end = None

        result = load_polygons(path, layer=layer)
        self.polygons = result.polygons

        self.scene = VisGraphScene(self)
        self.scene.set_polygons(self.polygons)
        self.view = GraphView(self.scene, self)
        self.view.pointClicked.connect(self.on_point_clicked)
        self.setCentralWidget(self.view)
        self._bounds = result.bounds
        self._fitted = False

        toolbar = self.addToolBar('View')
        toolbar.setMovable(False)
        self.toggle_edges_action = QAction('Show visibility graph', self)
        self.toggle_edges_action.setCheckable(True)
        self.toggle_edges_action.setChecked(True)
        self.toggle_edges_action.setEnabled(False)
        self.toggle_edges_action.toggled.connect(
            self.scene.set_vis_edges_visible)
        toolbar.addAction(self.toggle_edges_action)

        clear_action = QAction('Clear points', self)
        clear_action.triggered.connect(self.clear_points)
        toolbar.addAction(clear_action)

        self.busy_bar = QProgressBar(self)
        self.busy_bar.setRange(0, 0)  # indeterminate
        self.busy_bar.setMaximumWidth(160)
        self.statusBar().addPermanentWidget(self.busy_bar)

        skipped_note = ('' if not result.skipped else
                        ' ({} non-polygon geometries skipped)'.format(
                            result.skipped))
        self.statusBar().showMessage(
            'Building visibility graph ({} polygons)...{}'.format(
                len(self.polygons), skipped_note))

        self.worker = BuildWorker(self.polygons, workers=workers, parent=self)
        self.worker.finished_ok.connect(self.on_build_finished)
        self.worker.failed.connect(self.on_build_failed)
        self.worker.start()

    def showEvent(self, event):
        super().showEvent(event)
        # fitInView needs the viewport at its final size, which it only has
        # once the window is shown.
        if not self._fitted:
            self._fitted = True
            self.view.fit_bounds(*self._bounds)

    def on_build_finished(self, graph):
        self.visgraph = graph
        edges = graph.visgraph.get_edges()
        self.scene.set_vis_edges(edges)
        self.toggle_edges_action.setEnabled(True)
        self.busy_bar.hide()
        self.statusBar().showMessage(
            'Ready ({} visibility edges) - left-click sets start, '
            'right-click sets end'.format(len(edges)))

    def on_build_failed(self, message):
        self.busy_bar.hide()
        self.statusBar().showMessage(
            'Failed to build visibility graph: {}'.format(message))

    def on_point_clicked(self, x, y, button):
        if self.visgraph is None:
            return  # still building
        point, note = self._snap_outside(vg.Point(x, y))
        if button == Qt.MouseButton.LeftButton:
            self.start = point
            self.scene.set_start(point)
        elif button == Qt.MouseButton.RightButton:
            self.end = point
            self.scene.set_end(point)
        else:
            return
        self.update_path(note)

    def _snap_outside(self, point):
        """Move a point that lands inside an obstacle just outside of it."""
        polygon_id = self.visgraph.point_in_polygon(point)
        if polygon_id < 0:
            return point, ''
        snapped = self.visgraph.closest_point(point, polygon_id)
        return snapped, ' (point was inside an obstacle, snapped outside)'

    def clear_points(self):
        self.start = None
        self.end = None
        self.scene.set_start(None)
        self.scene.set_end(None)
        self.scene.set_path(None)
        if self.visgraph is not None:
            self.statusBar().showMessage(
                'Points cleared - left-click sets start, right-click sets end')

    def update_path(self, note=''):
        if self.start is None or self.end is None:
            self.statusBar().showMessage(
                ('Start set - right-click to set end' if self.end is None
                 else 'End set - left-click to set start') + note)
            return
        path = self.visgraph.shortest_path(self.start, self.end)
        if not path or len(path) < 2:
            self.scene.set_path(None)
            self.statusBar().showMessage('No path found' + note)
            return
        self.scene.set_path(path)
        length = sum(math.hypot(p2.x - p1.x, p2.y - p1.y)
                     for p1, p2 in zip(path, path[1:]))
        self.statusBar().showMessage(
            'Path: {} segments, length {:.6g}{}'.format(
                len(path) - 1, length, note))
