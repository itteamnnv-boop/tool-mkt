"""Bảng nhật ký dùng chung cho trang Nhật ký hoạt động."""
from __future__ import annotations

from datetime import datetime
import traceback

from PySide6.QtWidgets import QPlainTextEdit

from app.storage import history_store


class LogConsole(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logConsole")
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)
        self.setPlaceholderText("Nhật ký hoạt động sẽ hiển thị ở đây...")
        try:
            for row in history_store.list_activity_logs():
                self._append_entry(row["message"], row["level"], row["created_at"])
        except Exception:
            self._storage_error("Không thể tải nhật ký đã lưu.")

    def log(self, message: str, level: str = "info") -> None:
        created_at = datetime.now().isoformat(timespec="seconds")
        self._append_entry(message, level, created_at)
        try:
            history_store.add_activity_log(message, level, created_at)
        except Exception:
            self._storage_error("Không thể lưu nhật ký vào DB; bản ghi này chỉ hiển thị trong phiên hiện tại.")

    def clear(self) -> None:
        try:
            history_store.clear_activity_logs()
        except Exception:
            self._storage_error("Không thể xoá nhật ký trong DB. Nhật ký vẫn được giữ lại.")
            return
        super().clear()

    def _storage_error(self, message: str) -> None:
        # Never log recursively when the log database itself is unavailable.
        traceback.print_exc()
        self._append_entry(message, "error", datetime.now().isoformat(timespec="seconds"))

    def _append_entry(self, message: str, level: str, created_at: str) -> None:
        prefix = {"info": "•", "error": "✗", "success": "✓"}.get(level, "•")
        timestamp = datetime.fromisoformat(created_at).strftime("%d/%m/%Y %H:%M:%S")
        self.appendPlainText(f"[{timestamp}] {prefix} {message}")
