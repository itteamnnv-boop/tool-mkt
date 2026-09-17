"""A simple vertical timeline/stepper: numbered steps connected by a line, each with a
status (pending/active/done/error) and an optional expandable content area — used by the
Automation screen to show the pipeline's progress instead of one flat form."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from app.ui.widgets.liquid_glass import GlassCard

STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"

# (circle background, circle text color)
_CIRCLE_STYLE = {
    STATUS_PENDING: ("#303d49", "#a3b2bd"),
    STATUS_ACTIVE: ("#237783", "#d2f8fb"),
    STATUS_DONE: ("#24b47e", "#ffffff"),
    STATUS_ERROR: ("#e45d78", "#ffffff"),
    STATUS_SKIPPED: ("#303d49", "#a3b2bd"),
}


class TimelineStep(GlassCard):
    def __init__(self, index: int, title: str, is_last: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("timelineStep")
        self._index = index

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 18)
        outer.setSpacing(12)

        rail = QVBoxLayout()
        rail.setContentsMargins(0, 0, 0, 0)
        rail.setSpacing(0)
        self.circle = QLabel(str(index))
        self.circle.setFixedSize(28, 28)
        self.circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rail.addWidget(self.circle, 0, Qt.AlignmentFlag.AlignHCenter)
        self.line = QFrame()
        self.line.setFrameShape(QFrame.Shape.VLine)
        self.line.setObjectName("timelineLine")
        self.line.setMinimumHeight(24)
        self.line.setVisible(not is_last)
        rail.addWidget(self.line, 1, Qt.AlignmentFlag.AlignHCenter)
        rail_widget = QWidget()
        rail_widget.setLayout(rail)
        rail_widget.setFixedWidth(28)
        outer.addWidget(rail_widget)

        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 2, 0, 0)
        self.content_layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("timelineTitle")
        self.content_layout.addWidget(self.title_label)

        self.status_label = QLabel("Chưa bắt đầu")
        self.status_label.setObjectName("timelineStatus")
        self.status_label.setWordWrap(True)
        self.content_layout.addWidget(self.status_label)

        self.extra_container = QWidget()
        self.extra_layout = QVBoxLayout(self.extra_container)
        self.extra_layout.setContentsMargins(0, 6, 0, 0)
        self.extra_layout.setSpacing(6)
        self.extra_container.setVisible(False)
        self.content_layout.addWidget(self.extra_container)

        outer.addWidget(content_widget, 1)

        self.set_status(STATUS_PENDING, "Chưa bắt đầu")

    def set_status(self, status: str, message: str | None = None) -> None:
        bg, fg = _CIRCLE_STYLE.get(status, _CIRCLE_STYLE[STATUS_PENDING])
        self.circle.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 14px; font-weight: 600;"
        )
        if status == STATUS_DONE:
            self.circle.setText("✓")
        elif status == STATUS_ERROR:
            self.circle.setText("✗")
        elif status == STATUS_SKIPPED:
            self.circle.setText("–")
        else:
            self.circle.setText(str(self._index))
        if message is not None:
            self.status_label.setText(message)

    def set_extra_widget(self, widget: QWidget | None) -> None:
        while self.extra_layout.count():
            item = self.extra_layout.takeAt(0)
            existing = item.widget()
            if existing is not None:
                existing.setParent(None)
        if widget is not None:
            self.extra_layout.addWidget(widget)
        self.extra_container.setVisible(widget is not None)


class TimelineWidget(QWidget):
    def __init__(self, titles: list[str], parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.steps: list[TimelineStep] = []
        for i, title in enumerate(titles, start=1):
            step = TimelineStep(i, title, is_last=(i == len(titles)))
            self.steps.append(step)
            layout.addWidget(step)

    def reset(self) -> None:
        """Resets each step's status back to pending. Deliberately leaves each step's extra
        widget untouched — callers attach one persistent, reusable widget per step at build
        time (e.g. the review text box, the post button) rather than a fresh one per run, so
        detaching it here would let Qt garbage-collect it out from under those widgets."""
        for step in self.steps:
            step.set_status(STATUS_PENDING, "Chưa bắt đầu")
