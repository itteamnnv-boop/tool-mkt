"""Reusable checkable list of connected Facebook Pages — used by both the manual Post
screen and the automated pipeline so page-selection logic lives in exactly one place.

Built from real QCheckBox rows (via RowListWidget) instead of QListWidget items — see
row_list.py for why that avoids clipped text and stray empty space.
"""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app import config
from app.ui.widgets.row_list import RowListWidget


class PagesSelectorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        layout.addWidget(QLabel("Đăng lên Page nào:"))
        header_row.addStretch(1)
        select_all_btn = QPushButton("Chọn tất cả")
        select_all_btn.setObjectName("linkButton")
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        select_none_btn = QPushButton("Bỏ chọn")
        select_none_btn.setObjectName("linkButton")
        select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        refresh_btn = QPushButton("Làm mới")
        refresh_btn.setObjectName("linkButton")
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(select_all_btn)
        header_row.addWidget(select_none_btn)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        self.row_list = RowListWidget(height=130)
        layout.addWidget(self.row_list)

    def refresh(self) -> None:
        checked_ids = {page_id for page_id, cb in self._checkboxes.items() if cb.isChecked()}
        self.row_list.clear()
        self._checkboxes = {}

        pages = config.list_pages()
        if not pages:
            placeholder = QLabel("Chưa kết nối Page nào — vào tab 'Kết nối Facebook' trước.")
            placeholder.setObjectName("mutedHint")
            placeholder.setWordWrap(True)
            self.row_list.add_row(placeholder)
            return

        for page in pages:
            page_id = page.get("id")
            page_name = page.get("name") or page_id
            checkbox = QCheckBox(f"{page_name}   ·   ID: {page_id}")
            checkbox.setObjectName("pageCheckRow")
            checkbox.setChecked(page_id in checked_ids if checked_ids else True)
            self._checkboxes[page_id] = checkbox
            self.row_list.add_row(checkbox)

    def _set_all_checked(self, checked: bool) -> None:
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(checked)

    def selected_pages(self) -> list[dict]:
        """Returns [{"id", "name", "token"}, ...] for every checked, still-connected Page."""
        selected = []
        pages_by_id = {p["id"]: p for p in config.list_pages()}
        for page_id, checkbox in self._checkboxes.items():
            if not checkbox.isChecked():
                continue
            page = pages_by_id.get(page_id)
            if not page:
                continue
            token = config.get_page_token(page_id)
            if not token:
                continue
            selected.append({"id": page_id, "name": page.get("name") or page_id, "token": token})
        return selected
