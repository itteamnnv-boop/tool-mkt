"""A simple scrollable vertical list of real row widgets, at a fixed, modest height.

QListWidget + setItemWidget() requires manually snapshotting each row's sizeHint() up front,
which is fragile: if the row's font/metrics aren't fully resolved yet (e.g. app stylesheet
not polished at snapshot time), rows render with clipped text. Using ordinary child widgets
inside a normal QVBoxLayout avoids that — Qt's layout system sizes each row itself.

A fixed height (rather than trying to auto-shrink to content) is deliberate: dynamically
resizing a QScrollArea to its content's sizeHint fights the enclosing layout in ways that
depend on exactly how many parent layouts are nested and when Qt processes the resulting
LayoutRequest events, which made the list's height unpredictable in practice. A fixed
height with a scrollbar for overflow is the same trade-off any ordinary list box makes, and
never produces the "huge blank box under 1 row" bug this widget replaces.
"""
from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget


class RowListWidget(QScrollArea):
    def __init__(self, parent=None, height: int = 140):
        super().__init__(parent)
        self.setObjectName("rowList")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setFixedHeight(height)

        container = QWidget()
        container.setObjectName("rowListContainer")
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(4)
        self._layout.addStretch(1)
        self.setWidget(container)

    def clear(self) -> None:
        while self._layout.count() > 1:  # keep the trailing stretch at the end
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_row(self, widget: QWidget) -> None:
        self._layout.insertWidget(self._layout.count() - 1, widget)

    def is_empty(self) -> bool:
        return self._layout.count() <= 1
