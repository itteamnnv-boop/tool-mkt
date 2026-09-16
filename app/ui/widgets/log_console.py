"""Bảng nhật ký dùng chung cho trang Nhật ký hoạt động."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QPlainTextEdit


class LogConsole(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logConsole")
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)
        self.setPlaceholderText("Nhật ký hoạt động sẽ hiển thị ở đây...")

    def log(self, message: str, level: str = "info") -> None:
        prefix = {"info": "•", "error": "✗", "success": "✓"}.get(level, "•")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.appendPlainText(f"[{timestamp}] {prefix} {message}")
