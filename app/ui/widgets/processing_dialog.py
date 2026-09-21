"""Small floating dialog with a spinner + live status text, shown while the automation
pipeline runs. Without it, a long step (HeyGen video generation can take minutes) gives no
visual sign the app is still working — the timeline text updates, but only if the user is
looking at that tab. This dialog stays on top and updates regardless of which tab is active."""
from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout
from app.ui.widgets.process_scene import DEFAULT_STAGES, ProcessScene


class ProcessingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("processingDialog")
        self.setWindowTitle("Đang xử lý")
        self.setModal(False)
        self.setMinimumWidth(600)
        self.setMaximumWidth(760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Tiến trình tác vụ")
        title.setObjectName("pageHeader")
        title.setWordWrap(True)
        layout.addWidget(title)
        self.scene = ProcessScene()
        layout.addWidget(self.scene)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate — we don't know step durations up front
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        self.elapsed_label = QLabel("Đã chạy: 0 giây")
        layout.addWidget(self.elapsed_label)
        self.clock = QElapsedTimer()
        self.clock.start()
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._update_elapsed)

        hint = QLabel("Các bước cập nhật theo tác vụ thực tế. Có thể ẩn dialog để tiếp tục làm việc; tác vụ vẫn chạy nền.")
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.hide_btn = QPushButton("Ẩn")
        self.hide_btn.setObjectName("linkButton")
        self.hide_btn.clicked.connect(self.hide)
        layout.addWidget(self.hide_btn, 0, Qt.AlignmentFlag.AlignRight)

    def start(self, status: str, stages=None) -> None:
        self.scene.configure(stages or DEFAULT_STAGES)
        if stages is None:
            self.scene.set_stage("start", "done")
            self.scene.set_stage("process")
        self.clock.restart()
        self._update_elapsed()
        self.elapsed_timer.start()
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(status)
        self.show()
        self.raise_()
        self.activateWindow()

    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def set_stage(self, key: str, state: str = "active") -> None:
        self.scene.set_stage(key, state)

    def _update_elapsed(self):
        seconds = self.clock.elapsed() // 1000
        self.elapsed_label.setText(f"Đã chạy: {seconds // 60:02d}:{seconds % 60:02d}")

    def track(self, worker, status: str) -> None:
        """Show automatically for a single worker and follow its real signals."""
        self.start(status)
        worker.progress.connect(self.set_status)
        worker.finished.connect(self._worker_done)
        worker.error.connect(lambda message: self.finish(f"Lỗi: {message}", outcome="error"))
        worker.cancelled.connect(lambda: self.finish("Tác vụ đã dừng.", outcome="cancelled"))

    def _worker_done(self, result):
        failed = isinstance(result, list) and any(isinstance(item, dict) and item.get("ok") is False for item in result)
        self.finish("Tác vụ hoàn tất, có kết quả thất bại." if failed else "Tác vụ hoàn tất.", outcome="error" if failed else "done")

    def finish(self, status: str | None = None, outcome: str = "done") -> None:
        if status is not None:
            self.status_label.setText(status)
        self.scene.finish(outcome)
        self.elapsed_timer.stop()
        self._update_elapsed()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1 if outcome == "done" else 0)
        self.hide()
