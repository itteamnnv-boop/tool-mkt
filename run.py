"""Entry point: khởi động Claude Content Studio."""
import sys
import os
import traceback
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon

from app.ui.theme import apply_theme
from app.ui.main_window import MainWindow


class CodeReloader:
    """Restart the desktop app after source/style edits during local development."""

    def __init__(self, app: QApplication, window: MainWindow):
        self.app = app
        self.window = window
        self.root = Path(__file__).resolve().parent
        self._snapshot = self._take_snapshot()
        self._restarting = False
        self.timer = QTimer(app)
        self.timer.timeout.connect(self._check_for_changes)
        self.timer.start(1000)

    def _take_snapshot(self) -> dict[Path, int]:
        tracked = [self.root / "run.py"]
        app_dir = self.root / "app"
        tracked.extend(path for path in app_dir.rglob("*") if path.suffix in {".py", ".qss"})
        snapshot = {}
        for path in tracked:
            try:
                snapshot[path] = path.stat().st_mtime_ns
            except OSError:
                continue
        return snapshot

    def _check_for_changes(self) -> None:
        if self._restarting:
            return
        latest = self._take_snapshot()
        if latest == self._snapshot:
            return
        self._restarting = True
        self.timer.stop()
        self.window.toast.show_message("Đã phát hiện code mới. Ứng dụng sẽ tải lại...", "info")
        QTimer.singleShot(700, self._restart)

    def _restart(self) -> None:
        started = QProcess.startDetached(sys.executable, [str(self.root / "run.py"), *sys.argv[1:]])
        if started:
            self.app.quit()
            return
        self._restarting = False
        self._snapshot = self._take_snapshot()
        self.timer.start(1000)
        self.window.toast.show_message("Không thể tự tải lại ứng dụng.", "error")


def _install_exception_safety_net() -> None:
    """PySide6 aborts the whole process on an unhandled exception raised inside a Qt slot
    (e.g. a signal callback from a background worker). Without this hook, a single bug in
    one button's handler would silently close the entire app and lose all unsaved work."""

    def handle(exc_type, exc_value, exc_tb):
        traceback.print_exception(exc_type, exc_value, exc_tb)
        detail = "".join(traceback.format_exception_only(exc_type, exc_value)).strip()
        app = QApplication.instance()
        if app is not None:
            QMessageBox.critical(
                None,
                "Đã xảy ra lỗi",
                f"Có lỗi không mong muốn xảy ra:\n\n{detail}\n\n"
                "Chi tiết đầy đủ đã được in ra terminal. Ứng dụng vẫn tiếp tục chạy.",
            )

    sys.excepthook = handle


def main() -> int:
    app = QApplication(sys.argv)
    _install_exception_safety_net()
    app.setApplicationName("Claude Content Studio")
    app.setDesktopFileName("claude-content-studio")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "app" / "resources" / "studio.svg")))
    apply_theme(app)
    window = MainWindow()
    window.show()
    if os.environ.get("CLAUDE_STUDIO_NO_RELOAD") != "1" and not getattr(sys, "frozen", False):
        CodeReloader(app, window)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
