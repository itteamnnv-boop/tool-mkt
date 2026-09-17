"""Floating desktop chrome with native window movement and resizing."""
from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget
from app.ui.widgets.design import line_icon


class GlassTitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.host = window
        self.setObjectName("glassTitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(32)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)
        caption = QLabel("CONTENT STUDIO")
        caption.setObjectName("windowCaption")
        caption.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(caption, 1)
        for icon, tip, callback in [("minimize", "Thu nhỏ", window.showMinimized), ("maximize", "Phóng to / khôi phục", self.toggle_maximized)]:
            button = QPushButton()
            button.setObjectName("windowControl")
            button.setProperty("iconName", icon)
            button.setIcon(line_icon(icon))
            button.setIconSize(QSize(13, 13))
            button.setFixedSize(24, 24)
            button.setToolTip(tip)
            button.setAccessibleName(tip)
            button.clicked.connect(callback)
            layout.addWidget(button)
        close = QPushButton()
        close.setObjectName("windowClose")
        close.setProperty("iconName", "close")
        close.setIcon(line_icon("close"))
        close.setIconSize(QSize(13, 13))
        close.setFixedSize(24, 24)
        close.setToolTip("Đóng ứng dụng")
        close.setAccessibleName("Đóng ứng dụng")
        close.clicked.connect(window.close)
        layout.addWidget(close)
        window.installEventFilter(self)

    def toggle_maximized(self):
        if self.host.isMaximized():
            self.host.showNormal()
        else:
            self.host.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.host.windowHandle():
            self.host.windowHandle().startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            event.accept()

    def eventFilter(self, watched, event):
        if watched is self.host and event.type() == QEvent.Type.MouseButtonPress and not self.host.isMaximized():
            if event.button() == Qt.MouseButton.LeftButton:
                point = event.position()
                edges = Qt.Edge(0)
                if point.x() < 12: edges |= Qt.Edge.LeftEdge
                if point.x() >= self.host.width() - 12: edges |= Qt.Edge.RightEdge
                if point.y() < 12: edges |= Qt.Edge.TopEdge
                if point.y() >= self.host.height() - 12: edges |= Qt.Edge.BottomEdge
                if edges and self.host.windowHandle():
                    return self.host.windowHandle().startSystemResize(edges)
        return super().eventFilter(watched, event)
