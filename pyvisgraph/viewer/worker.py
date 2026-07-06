"""Background thread for the blocking VisGraph.build call."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

import pyvisgraph as vg


class BuildWorker(QThread):
    """Builds the visibility graph off the UI thread.

    progress(done, total) reports how many vertices have had their
    visibility computed; the signal crosses to the UI thread via Qt's
    queued connection.
    """

    finished_ok = pyqtSignal(object)  # the built vg.VisGraph
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # vertices done, total vertices

    def __init__(self, polygons: list[list[vg.Point]], workers: int = 1,
                 lazy: bool = False, parent: QObject | None = None):
        super().__init__(parent)
        self._polygons = polygons
        self._workers = workers
        self._lazy = lazy

    def run(self):
        try:
            graph = vg.VisGraph()
            graph.build(self._polygons, workers=self._workers, status=False,
                        progress=self.progress.emit, lazy=self._lazy)
        except Exception as e:  # surface any build failure in the UI
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(graph)
