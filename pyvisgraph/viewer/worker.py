"""Background thread for the blocking VisGraph.build call."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

import pyvisgraph as vg


class BuildWorker(QThread):
    """Builds the visibility graph off the UI thread.

    build() has no progress callback, so the UI shows an indeterminate
    busy state until finished_ok/failed fires.
    """

    finished_ok = pyqtSignal(object)  # the built vg.VisGraph
    failed = pyqtSignal(str)

    def __init__(self, polygons: list[list[vg.Point]], workers: int = 1,
                 parent: QObject | None = None):
        super().__init__(parent)
        self._polygons = polygons
        self._workers = workers

    def run(self):
        try:
            graph = vg.VisGraph()
            graph.build(self._polygons, workers=self._workers, status=False)
        except Exception as e:  # surface any build failure in the UI
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(graph)
