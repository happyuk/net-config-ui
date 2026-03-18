from PySide6.QtCore import QObject, QThread

class ThreadRunner(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._threads = []  # keep refs so GC doesn't kill them

    def run(self, worker, *, on_log=None, on_error=None,
            on_progress=None, on_finished=None):
        thread = QThread()
        worker.moveToThread(thread)

        # --- Optional signal wiring ---
        if hasattr(worker, "log") and on_log:
            worker.log.connect(on_log)

        if hasattr(worker, "error") and on_error:
            worker.error.connect(on_error)

        if hasattr(worker, "progress") and on_progress:
            worker.progress.connect(on_progress)

        if hasattr(worker, "finished"):
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)

            if on_finished:
                from PySide6.QtCore import Qt
                worker.finished.connect(on_finished, Qt.QueuedConnection)

        thread.finished.connect(thread.deleteLater)

        # Start execution
        thread.started.connect(lambda: worker.run())
        thread.start()

        # Keep reference
        self._threads.append(thread)

        # Cleanup reference when done
        thread.finished.connect(
            lambda: self._threads.remove(thread) if thread in self._threads else None
        )

        return thread