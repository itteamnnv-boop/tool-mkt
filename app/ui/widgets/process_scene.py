"""A small native 2D flow scene driven by real task stages."""
import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.widgets.design import line_icon

DEFAULT_STAGES = [("start", "Bắt đầu", "dashboard"), ("process", "Đang xử lý", "automation"), ("result", "Nhận kết quả", "logs")]
STATE_LABELS = {"waiting": "Chờ", "active": "Đang chạy", "done": "Hoàn tất", "error": "Có lỗi", "skipped": "Bỏ qua", "cancelled": "Đã dừng"}


class ProcessScene(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Mô phỏng 2D tiến trình tác vụ")
        self.stages = []
        self.states = {}
        self.running = False
        self.clock = QElapsedTimer()
        self.clock.start()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.update)
        self.configure(DEFAULT_STAGES)
        self.running = False

    def sizeHint(self):
        return QSize(600, 126 * max(1, math.ceil(len(self.stages) / 3)))

    def configure(self, stages):
        self.stages = list(stages or DEFAULT_STAGES)
        self.states = {key: "waiting" for key, _, _ in self.stages}
        self.running = True
        self.clock.restart()
        self.setMinimumHeight(self.sizeHint().height())
        self.updateGeometry()
        self._refresh_timer()
        self.update()

    def set_stage(self, key, state="active"):
        if key not in self.states or state not in STATE_LABELS:
            return
        if state == "active":
            for other, old_state in self.states.items():
                if other != key and old_state == "active":
                    self.states[other] = "done"
        self.states[key] = state
        self.update()

    def finish(self, outcome="done"):
        if outcome == "done":
            for key, state in self.states.items():
                if state in {"waiting", "active"}:
                    self.states[key] = "done"
        else:
            for key, state in self.states.items():
                if state == "active":
                    self.states[key] = outcome
        self.running = False
        self._refresh_timer()
        self.update()

    def _refresh_timer(self):
        if self.running and self.isVisible():
            self.timer.start()
        else:
            self.timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_timer()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        light = QApplication.instance().property("glassStyle") == "crystal"
        text = QColor("#283744" if light else "#f4f4fa")
        muted = QColor("#647787" if light else "#9ea8bb")
        accent = QColor("#008dba" if light else "#ae8cff")
        gap, margin = 22, 8
        tile_width = (self.width() - margin * 2 - gap * 2) / 3
        tile_height = 104
        positions = []
        for index in range(len(self.stages)):
            row, col = divmod(index, 3)
            if row % 2:
                col = 2 - col
            positions.append(QRectF(margin + col * (tile_width + gap), row * 126 + 8, tile_width, tile_height))
        for index in range(len(positions) - 1):
            current, following = positions[index], positions[index + 1]
            path = QPainterPath()
            if index // 3 == (index + 1) // 3:
                forward = current.x() < following.x()
                start = QPointF(current.right() if forward else current.left(), current.center().y())
                end = QPointF(following.left() if forward else following.right(), following.center().y())
            else:
                start = QPointF(current.center().x(), current.bottom())
                end = QPointF(following.center().x(), following.top())
            path.moveTo(start)
            path.lineTo(end)
            painter.setPen(QPen(QColor("#c0ced9" if light else "#3b4154"), 2))
            painter.drawPath(path)
            if self.running and self.states[self.stages[index + 1][0]] == "active":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(accent)
                for offset in (0, 0.5):
                    position = path.pointAtPercent((self.clock.elapsed() / 1400 + offset) % 1)
                    painter.drawEllipse(position, 3, 3)
        for index, (key, label, icon) in enumerate(self.stages):
            rect = positions[index]
            state = self.states[key]
            color = {"active": accent, "done": QColor("#169b78"), "error": QColor("#e0526f"),
                     "cancelled": QColor("#d68b35")}.get(state, muted)
            if state == "active" and self.running:
                glow = QColor(color)
                glow.setAlpha(int(40 + 25 * (1 + math.sin(self.clock.elapsed() / 400))))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(glow, 5))
                painter.drawRoundedRect(rect, 16, 16)
            painter.setPen(QPen(color if state != "waiting" else QColor("#c2cdd6" if light else "#3f465c"), 1.3))
            painter.setBrush(QColor("#f1f6fc" if light else "#192032"))
            painter.drawRoundedRect(rect, 16, 16)
            line_icon(icon, color.name()).paint(painter, int(rect.x() + 14), int(rect.y() + 14), 24, 24)
            font = QFont(self.font())
            font.setPixelSize(12)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            painter.setPen(text)
            painter.drawText(rect.adjusted(14, 45, -12, -20), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, label)
            font.setPixelSize(11)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(rect.adjusted(44, 12, -8, -62), Qt.AlignmentFlag.AlignVCenter, STATE_LABELS[state])
        painter.end()
