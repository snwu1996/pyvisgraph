"""Main window wiring the loader, build worker, scene and interaction."""
from __future__ import annotations

import math
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QShowEvent
from PyQt6.QtWidgets import (QFileDialog, QMainWindow, QMessageBox,
                             QProgressBar)

import pyvisgraph as vg

from pyvisgraph.viewer.loader import load_polygons
from pyvisgraph.viewer.scene import VisGraphScene
from pyvisgraph.viewer.view import GraphView
from pyvisgraph.viewer.worker import BuildWorker

FILE_FILTER = ('Geometry files (*.kml *.geojson *.json *.shp *.gpkg *.zip);;'
               'All files (*)')
CLICK_HINT = 'click to set start, click again to set end'


class MainWindow(QMainWindow):

    def __init__(self, path: str, workers: int = 1,
                 layer: str | None = None):
        super().__init__()
        self.resize(1000, 750)

        self.workers = workers
        self.worker = None
        self.visgraph = None
        self.start = None
        self.end = None
        self.polygons = []
        self._bounds = None
        self._fitted = False

        self.scene = VisGraphScene(self)
        self.view = GraphView(self.scene, self)
        self.view.pointClicked.connect(self.on_point_clicked)
        self.setCentralWidget(self.view)

        file_menu = self.menuBar().addMenu('&File')
        open_action = QAction('&Open...', self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file_dialog)
        file_menu.addAction(open_action)
        quit_action = QAction('&Quit', self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

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

        self.load_file(path, layer=layer)

    def load_file(self, path: str, layer: str | None = None):
        """Load a geometry file and start building its visibility graph.

        Raises on unreadable/polygon-free files, leaving the current
        state untouched when called from the Open dialog.
        """
        result = load_polygons(path, layer=layer)

        self.setWindowTitle('pyvisgraph viewer - {}'.format(
            os.path.basename(path)))
        self.polygons = result.polygons
        self.visgraph = None
        self.start = None
        self.end = None
        self.scene.set_start(None)
        self.scene.set_end(None)
        self.scene.set_path(None)
        self.scene.set_vis_edges([])
        self.scene.set_polygons(self.polygons)
        self._bounds = result.bounds
        if self._fitted:
            self.view.fit_bounds(*self._bounds)

        self.toggle_edges_action.setEnabled(False)
        self.busy_bar.show()
        skipped_note = ('' if not result.skipped else
                        ' ({} non-polygon geometries skipped)'.format(
                            result.skipped))
        self.statusBar().showMessage(
            'Building visibility graph ({} polygons)...{}'.format(
                len(self.polygons), skipped_note))

        self.worker = BuildWorker(self.polygons, workers=self.workers,
                                  parent=self)
        self.worker.finished_ok.connect(self.on_build_finished)
        self.worker.failed.connect(self.on_build_failed)
        self.worker.start()

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open geometry file', '', FILE_FILTER)
        if not path:
            return
        try:
            self.load_file(path)
        except Exception as e:
            QMessageBox.critical(self, 'Load failed',
                                 'Could not load {}:\n{}'.format(path, e))

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        # fitInView needs the viewport at its final size, which it only has
        # once the window is shown.
        if not self._fitted:
            self._fitted = True
            self.view.fit_bounds(*self._bounds)

    def on_build_finished(self, graph: vg.VisGraph):
        if self.sender() is not self.worker:
            return  # stale result from a build superseded by File > Open
        self.visgraph = graph
        edges = graph.visgraph.get_edges()
        self.scene.set_vis_edges(edges)
        self.toggle_edges_action.setEnabled(True)
        self.busy_bar.hide()
        self.statusBar().showMessage(
            'Ready ({} visibility edges) - {}'.format(len(edges), CLICK_HINT))

    def on_build_failed(self, message: str):
        if self.sender() is not self.worker:
            return
        self.busy_bar.hide()
        self.statusBar().showMessage(
            'Failed to build visibility graph: {}'.format(message))

    def on_point_clicked(self, x: float, y: float, button: Qt.MouseButton):
        if self.visgraph is None or button != Qt.MouseButton.LeftButton:
            return
        point, note = self._snap_outside(vg.Point(x, y))
        if self.start is None or self.end is not None:
            # First click of a new pair: set the start, drop any old path.
            self.start = point
            self.end = None
            self.scene.set_start(point)
            self.scene.set_end(None)
            self.scene.set_path(None)
        else:
            self.end = point
            self.scene.set_end(point)
        self.update_path(note)

    def _snap_outside(self, point: vg.Point):
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
            self.statusBar().showMessage('Points cleared - ' + CLICK_HINT)

    def update_path(self, note: str = ''):
        if self.end is None:
            self.statusBar().showMessage(
                'Start set - click again to set end' + note)
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
