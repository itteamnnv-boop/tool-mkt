"""A scalable media illustration drawn directly in Qt."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QStyle, QStyleOption, QWidget


class StudioHero(QWidget):
    def paintEvent(self, event):
        option = QStyleOption()
        option.initFrom(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, option, painter, self)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 22, 22)
        painter.setClipPath(clip)
        painter.setOpacity(0.65 if self.width() > 700 else 0.24)
        painter.translate(self.width() - 135, self.height() * 0.43)
        painter.rotate(16)
        for offset, color in [(40, "#aeb9b9"), (20, "#8796a5"), (0, "#4c5f74")]:
            rect = QRectF(-70 + offset, -88 - offset / 2, 166, 216)
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0, QColor(color))
            gradient.setColorAt(1, QColor("#252c3a"))
            painter.setBrush(gradient)
            painter.setPen(QPen(QColor(255, 255, 255, 85), 1))
            painter.drawRoundedRect(rect, 18, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(231, 224, 197, 210))
        painter.drawEllipse(QRectF(34, -58, 26, 26))
        mountains = QPainterPath()
        mountains.moveTo(-58, 42)
        mountains.lineTo(-10, -23)
        mountains.lineTo(28, 24)
        mountains.lineTo(51, 0)
        mountains.lineTo(84, 42)
        mountains.closeSubpath()
        painter.setBrush(QColor(190, 203, 200, 145))
        painter.drawPath(mountains)
        painter.setPen(QPen(QColor(240, 242, 235, 125), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(-48, 74, 62, 74)
        painter.drawLine(-48, 89, 20, 89)
        painter.end()
