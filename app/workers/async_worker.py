"""Generic QThread wrapper so any blocking call (Claude/OpenAI/HeyGen/Facebook) runs off the UI thread."""
from __future__ import annotations

import inspect
import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, QTimer, Signal


class Worker(QThread):
    # Result signals are emitted from run(), before the native thread has stopped.
    # A callback may replace its owner's Worker reference to start the next step.
    _active_workers = set()
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)
    thumbnail = Signal(str)
    stage = Signal(str, str)
    cancelled = Signal()

    def __init__(self, fn: Callable[..., Any], *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        try:
            params = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            params = {}
        if "on_progress" in params:
            self._kwargs.setdefault("on_progress", lambda msg: self.progress.emit(str(msg)))
        if "on_thumbnail" in params:
            self._kwargs.setdefault("on_thumbnail", lambda url: self.thumbnail.emit(str(url)))
        if "on_stage" in params:
            self._kwargs.setdefault("on_stage", lambda key, state: self.stage.emit(str(key), str(state)))
        self.finished.connect(self._release_when_stopped)
        self.error.connect(self._release_when_stopped)
        self.cancelled.connect(self._release_when_stopped)

    def start(self, priority=QThread.Priority.InheritPriority):
        self._active_workers.add(self)
        try:
            super().start(priority)
        except Exception:
            self._active_workers.discard(self)
            raise

    def _release_when_stopped(self):
        if self.isRunning():
            QTimer.singleShot(10, self._release_when_stopped)
        else:
            self._active_workers.discard(self)

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            if getattr(exc, "is_cancelled", False):
                # A deliberate user-requested stop (e.g. HeyGen's GenerationCancelled) is not
                # a failure — report it on its own signal so callers don't show an error dialog.
                self.cancelled.emit()
            else:
                traceback.print_exc()
                self.error.emit(str(exc))
        else:
            self.finished.emit(result)
