"""Shared layout and vector icons for the charcoal/cyan workspace."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

_PATHS = {
    "dashboard": '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M7 16v-3M12 16V8M17 16v-5"/>',
    "content": '<path d="M4 4h11v16H4zM8 8h4M8 12h4M8 16h3M17 5l3 3-5 5-3 1 1-3z"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8" cy="8" r="1.5"/><path d="m4 17 5-5 4 4 3-3 4 4"/>',
    "video": '<rect x="3" y="5" width="18" height="14" rx="4"/><path d="m10 9 5 3-5 3z"/>',
    "gallery": '<rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="3" width="8" height="8" rx="2"/><rect x="3" y="13" width="8" height="8" rx="2"/><rect x="13" y="13" width="8" height="8" rx="2"/>',
    "facebook": '<path d="m3 11 18-8-6 18-4-7-8-3zM11 14 21 3"/>',
    "facebook_connect": '<path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" transform="translate(1 0) scale(.9)"/>',
    "tiktok": '<circle cx="11" cy="17" r="3"/><path d="M14 17V5l6 2"/>',
    "tiktok_connect": '<path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" transform="translate(1 0) scale(.9)"/>',
    "youtube": '<rect x="3" y="6" width="18" height="12" rx="4"/><path d="m10 9.5 5 2.5-5 2.5z"/>',
    "youtube_connect": '<path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" transform="translate(1 0) scale(.9)"/>',
    "automation": '<path d="m13 2-9 12h7l-1 8 10-13h-7z"/>',
    "logs": '<rect x="4" y="3" width="16" height="18" rx="5"/><path d="M8 8h8M8 12h8M8 16h4"/>',
    "settings": '<path d="m9 3 1-2h4l1 2 3 2 2 1v4l-2 2v3l1 2-3 3-3-1h-3l-2 1-3-3 1-3v-3l-2-2V6l3-1z" transform="translate(2 2) scale(.85)"/><circle cx="12" cy="12" r="3"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="4"/><path d="M7 2v6M17 2v6M3 11h18M8 15h1M15 15h1"/>',
    "group": '<path d="m6 9 6 6 6-6"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
}


def line_icon(name: str, color: str = "#89949e") -> QIcon:
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
           f'viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.5" '
           f'stroke-linecap="round" stroke-linejoin="round">{_PATHS[name]}</g></svg>')
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def card(title: str) -> tuple[QWidget, QVBoxLayout]:
    panel = QWidget()
    panel.setObjectName("card")
    outer = QVBoxLayout(panel)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    heading = QLabel(title)
    heading.setObjectName("cardTitle")
    heading.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    outer.addWidget(heading)
    body = QWidget()
    content = QVBoxLayout(body)
    content.setContentsMargins(18, 16, 18, 18)
    content.setSpacing(8)
    outer.addWidget(body, 1)
    return panel, content


def arrange_cards(layout: QVBoxLayout, groups: list[tuple[str, list[int]]]) -> None:
    """Keep the page heading; move existing controls into named, equal-width cards.

    Indices refer to items after the heading. Widgets and their signals stay intact.
    Only editor/preview regions expand; labels never absorb surplus vertical space.
    """
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(18)
    items = []
    while layout.count() > 1:
        items.append(layout.takeAt(1))
    row = QHBoxLayout()
    row.setSpacing(20)
    used = {i for _, indices in groups for i in indices}
    for index, item in enumerate(items):
        if index not in used and item.widget():
            item.widget().hide()
            item.widget().deleteLater()
    for title, indices in groups:
        panel, body = card(title)
        expanding = False
        for index in indices:
            widget = items[index].widget()
            child_layout = items[index].layout()
            if widget:
                body.addWidget(widget)
            elif child_layout:
                child_layout.setParent(None)
                body.addLayout(child_layout)
            else:
                body.addItem(items[index])
            if isinstance(widget, QTextEdit) or (widget and widget.objectName() == "mediaPreview"):
                if widget.maximumHeight() > 200:
                    body.setStretch(body.count() - 1, 1)
                    expanding = True
        if not expanding:
            body.addStretch(1)
        row.addWidget(panel, 1)
    layout.addLayout(row, 1)


def compact_labels(widget: QWidget) -> None:
    for combo in widget.findChildren(QComboBox):
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(10)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setToolTip(combo.currentText())
        combo.currentTextChanged.connect(combo.setToolTip)
    for label in widget.findChildren(QLabel):
        if label.objectName() == "mediaPreview":
            continue
        if label.objectName() == "cardTitle":
            continue
        if label.objectName() != "pageHeader":
            label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    for form in widget.findChildren(QFormLayout):
        if form.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapAllRows:
            for row in range(form.rowCount()):
                item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if item and isinstance(item.widget(), QLabel):
                    item.widget().setWordWrap(False)
