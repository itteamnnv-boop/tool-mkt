"""Small floating dialog with a spinner + live status text, shown while the automation
pipeline runs. Without it, a long step (HeyGen video generation can take minutes) gives no
visual sign the app is still working — the timeline text updates, but only if the user is
looking at that tab. This dialog stays on top and updates regardless of which tab is active."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout


class ProcessingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("processingDialog")
        self.setWindowTitle("Đang xử lý")
        self.setModal(False)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QLabel("🚀 Quy trình tự động đang chạy...")
        title.setObjectName("pageHeader")
        title.setWordWrap(True)
        layout.addWidget(title)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate — we don't know step durations up front
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        hint = QLabel("Có thể ẩn cửa sổ này — quy trình vẫn tiếp tục chạy nền, xem lại tiến trình ở tab Tự động hoá.")
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.hide_btn = QPushButton("Ẩn")
        self.hide_btn.setObjectName("linkButton")
        self.hide_btn.clicked.connect(self.hide)
        layout.addWidget(self.hide_btn, 0, Qt.AlignmentFlag.AlignRight)

    def start(self, status: str) -> None:
        self.status_label.setText(status)
        self.show()
        self.raise_()
        self.activateWindow()

    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def finish(self, status: str | None = None) -> None:
        if status is not None:
            self.status_label.setText(status)
        self.hide()
