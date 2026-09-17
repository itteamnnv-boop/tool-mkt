"""Trang nhật ký hoạt động dùng chung cho toàn bộ ứng dụng."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui.widgets.log_console import LogConsole
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.liquid_glass import GlassCard


class LogTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        header_row = QHBoxLayout()
        header_row.addWidget(
            make_page_header(
                "📋 Nhật ký hoạt động",
                "Theo dõi tiến trình, kết quả và lỗi phát sinh từ tất cả chức năng.",
            ),
            1,
        )

        self.clear_btn = QPushButton("Xoá nhật ký")
        self.clear_btn.setObjectName("linkButton")
        self.clear_btn.setToolTip("Xoá toàn bộ nội dung nhật ký đang hiển thị")
        header_row.addWidget(self.clear_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        console_wrapper = GlassCard()
        console_wrapper.setObjectName("logWrapper")
        console_layout = QVBoxLayout(console_wrapper)
        console_layout.setContentsMargins(8, 8, 8, 8)
        console_layout.setSpacing(0)

        console_header = QLabel("●  NHẬT KÝ PHIÊN LÀM VIỆC")
        console_header.setObjectName("logHeader")
        console_layout.addWidget(console_header)

        self.console = LogConsole()
        console_layout.addWidget(self.console, 1)
        layout.addWidget(console_wrapper, 1)

        self.clear_btn.clicked.connect(self.console.clear)
