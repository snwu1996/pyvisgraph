"""Main window wiring the loader, build worker, scene and interaction."""
from __future__ import annotations

import math
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QShowEvent
from PyQt6.QtWidgets import (QFileDialog, QMainWindow, QMessageBox,
                             QProgressBar, QStatusBar)

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
        self.worker: BuildWorker | None = None
        self.visgraph: vg.VisGraph | None = None
        self.start: vg.Point | None = None
        self.end: vg.Point | None = None
        self.polygons: list[list[vg.Point]] = []
        self._bounds: tuple[float, float, float, float] | None = None
        self._fitted = False

        self.scene = VisGraphScene(self)
        self.view = GraphView(self.scene, self)
        self.view.pointClicked.connect(self.on_point_clicked)
        self.setCentralWidget(self.view)

        menu_bar = self.menuBar()
        assert menu_bar is not None
        file_menu = menu_bar.addMenu('&File')
        assert file_menu is not None
        open_action = QAction('&Open...', self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file_dialog)
        file_menu.addAction(open_action)
        quit_action = QAction('&Quit', self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        toolbar = self.addToolBar('View')
        assert toolbar is not None
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
        self._status_bar().addPermanentWidget(self.busy_bar)

        self.load_file(path, layer=layer)

    def _status_bar(self) -> QStatusBar:
        bar = self.statusBar()
        assert bar is not None  # QMainWindow creates one on demand
        return bar

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
        # Show the shapes as authored; the graph is built on the dissolved
        # polygons, which outline the same solid area.
        self.scene.set_polygons(result.raw_polygons)
        self._bounds = result.bounds
        if self._fitted:
            self.view.fit_bounds(*self._bounds)

        self.toggle_edges_action.setEnabled(False)
        self.busy_bar.show()
        skipped_note = ('' if not result.skipped else
                        ' ({} non-polygon geometries skipped)'.format(
                            result.skipped))
        self._status_bar().showMessage(
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

    # PyQt6's stubs name the parameter a0 and allow None.
    def showEvent(self, a0: QShowEvent | None):
        super().showEvent(a0)
        # fitInView needs the viewport at its final size, which it only has
        # once the window is shown.
        if not self._fitted and self._bounds is not None:
            self._fitted = True
            self.view.fit_bounds(*self._bounds)

    def on_build_finished(self, graph: vg.VisGraph):
        if self.sender() is not self.worker:
            return  # stale result from a build superseded by File > Open
        self.visgraph = graph
        assert graph.visgraph is not None
        edges = graph.visgraph.get_edges()
        self.scene.set_vis_edges(edges)
        self.toggle_edges_action.setEnabled(True)
        self.busy_bar.hide()
        self._status_bar().showMessage(
            'Ready ({} visibility edges) - {}'.format(len(edges), CLICK_HINT))

    def on_build_failed(self, message: str):
        if self.sender() is not self.worker:
            return
        self.busy_bar.hide()
        self._status_bar().showMessage(
            'Failed to build visibility graph: {}'.format(message))

    def on_point_clicked(self, x: float, y: float, button: Qt.MouseButton):
        if self.visgraph is None or button != Qt.MouseButton.LeftButton:
            return
        point = vg.Point(x, y)
        note = (' (point is inside an obstacle)'
                if self.visgraph.point_in_solid(point) else '')
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

    def clear_points(self):
        self.start = None
        self.end = None
        self.scene.set_start(None)
        self.scene.set_end(None)
        self.scene.set_path(None)
        if self.visgraph is not None:
            self._status_bar().showMessage('Points cleared - ' + CLICK_HINT)

    def update_path(self, note: str = ''):
        if self.visgraph is None or self.start is None or self.end is None:
            self._status_bar().showMessage(
                'Start set - click again to set end' + note)
            return
        # A point in solid obstacle space can never be on a valid path; the
        # search is not run for it as it may thread through the boundary.
        # Points in the hole of a donut-shaped obstacle are free space and
        # get a real search (paths within the hole, none to the outside).
        blocked = [name for name, p in (('start', self.start),
                                        ('end', self.end))
                   if self.visgraph.point_in_solid(p)]
        if blocked:
            what = ('both points are' if len(blocked) == 2 else
                    'the {} point is'.format(blocked[0]))
            self.scene.set_path(None)
            self._status_bar().showMessage(
                'No path found: {} inside an obstacle'.format(what))
            return
        path = self.visgraph.shortest_path(self.start, self.end)
        if not path or len(path) < 2:
            self.scene.set_path(None)
            self._status_bar().showMessage('No path found' + note)
            return
        self.scene.set_path(path)
        length = sum(math.hypot(p2.x - p1.x, p2.y - p1.y)
                     for p1, p2 in zip(path, path[1:]))
        self._status_bar().showMessage(
            'Path: {} segments, length {:.6g}{}'.format(
                len(path) - 1, length, note))
