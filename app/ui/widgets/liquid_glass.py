"""Code-native glass rims and restrained elevation for existing Qt controls."""
from PySide6.QtCore import QElapsedTimer, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QConicalGradient, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QPushButton, QStyle, QStyleOption, QWidget


class GlassCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rim_clock = QElapsedTimer()
        self._rim_clock.start()
        self._rim_timer = QTimer(self)
        self._rim_timer.setInterval(33)
        self._rim_timer.timeout.connect(self.update)

    def showEvent(self, event):
        super().showEvent(event)
        self._rim_timer.start()

    def hideEvent(self, event):
        self._rim_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, option, painter, self)
        bounds = QRectF(self.rect()).adjusted(2, 2, -2, -4)
        radius = min(24, bounds.height() / 2)
        accent = {"contents": "#f1b6ca", "images": "#8be2e0", "videos": "#b6a0f5", "posts": "#9ce2c6"}.get(self.property("metric"))
        rim = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        rim.setColorAt(0, QColor(255, 255, 255, 215))
        rim.setColorAt(0.35, QColor(255, 255, 255, 40))
        rim.setColorAt(0.65, QColor(255, 255, 255, 12))
        finish = QColor(accent or "#ffffff")
        finish.setAlpha(170)
        rim.setColorAt(1, finish)
        crystal = QApplication.instance().property("glassStyle") == "crystal"
        if crystal:
            rim.setColorAt(0, QColor(255, 255, 255, 245))
            rim.setColorAt(0.22, QColor(149, 196, 224, 200))
            rim.setColorAt(0.35, QColor(90, 120, 145, 100))
            rim.setColorAt(0.65, QColor(205, 213, 247, 170))
            rim.setColorAt(0.82, QColor(117, 225, 234, 210))
            rim.setColorAt(1, QColor(247, 210, 132, 230))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(34, 37, 48, 45), 2.5))
        painter.drawRoundedRect(bounds.translated(0, 1.5), radius, radius)
        painter.setPen(QPen(rim, 2.25 if crystal else 1.5))
        painter.drawRoundedRect(bounds, radius, radius)
        inner = bounds.adjusted(2, 2, -2, -2)
        reflection = QLinearGradient(inner.topLeft(), inner.bottomLeft())
        reflection.setColorAt(0, QColor(255, 255, 255, 80))
        reflection.setColorAt(0.3, QColor(255, 255, 255, 0))
        reflection.setColorAt(0.75, QColor(255, 255, 255, 0))
        reflection.setColorAt(1, QColor(255, 255, 255, 70))
        painter.setPen(QPen(reflection, 1))
        painter.drawRoundedRect(inner, max(0, radius - 2), max(0, radius - 2))
        # Rotate a short luminous trail on the rim without filling the card body.
        angle = -(self._rim_clock.elapsed() % 6000) * 360 / 6000
        moving_rim = QConicalGradient(bounds.center(), angle)
        color = QColor(accent or ("#008dba" if crystal else "#b6a0f5"))
        if crystal:
            color = QColor("#008dba")
        for stop, alpha in ((0, 0), (0.70, 0), (0.82, 40), (0.92, 150), (0.96, 245), (1, 0)):
            glow_color = QColor(color)
            glow_color.setAlpha(alpha)
            moving_rim.setColorAt(stop, glow_color)
        # Broad faint strokes provide glow; the narrow stroke keeps the edge crisp.
        for width, opacity in ((7, 0.10), (4, 0.25), (1.8, 1.0)):
            painter.setOpacity(opacity)
            painter.setPen(QPen(moving_rim, width))
            painter.drawRoundedRect(bounds, radius, radius)
        painter.end()


def apply_button_elevation(root):
    crystal = QApplication.instance().property("glassStyle") == "crystal"
    for button in root.findChildren(QPushButton):
        name = button.objectName()
        # Compact secondary controls often sit in tight form rows that clip a shadow.
        if name != "primaryButton":
            continue
        shadow = button.graphicsEffect()
        if shadow is None:
            shadow = QGraphicsDropShadowEffect(button)
            shadow.setBlurRadius(12)
            shadow.setOffset(0, 3)
            button.setGraphicsEffect(shadow)
        if isinstance(shadow, QGraphicsDropShadowEffect):
            shadow.setColor(QColor(204, 108, 38, 70) if crystal else QColor(95, 58, 173, 55))
