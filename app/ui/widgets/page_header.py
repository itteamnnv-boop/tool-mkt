"""Reusable page title block used at the top of each sidebar page."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


def make_page_header(title: str, subtitle: str = "") -> QWidget:
    wrapper = QWidget()
    wrapper.setObjectName("pageHeaderBlock")
    # QWidget mặc định có thể nhận thêm chiều cao từ QVBoxLayout, khiến khoảng cách
    # giữa tiêu đề và form bị kéo giãn khi cửa sổ lớn.
    wrapper.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 8)
    layout.setSpacing(8)

    title_label = QLabel(title.split(" ", 1)[-1] if not title[0].isalnum() else title)
    title_label.setObjectName("pageHeader")
    layout.addWidget(title_label)

    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("pageSubheader")
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

    return wrapper
