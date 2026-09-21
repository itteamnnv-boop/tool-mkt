"""Floating desktop chrome with native window movement and resizing."""
from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractSlider, QAbstractSpinBox,
    QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QMenuBar, QPlainTextEdit, QPushButton, QTextEdit, QWidget,
)
from app.ui.widgets.design import line_icon


class GlassTitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.host = window
        self._drag_offset = None
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
        QApplication.instance().installEventFilter(self)

    def toggle_maximized(self):
        if self.host.isMaximized():
            self.host.showNormal()
        else:
            self.host.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._start_move(event):
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            event.accept()

    def _is_background(self, widget):
        protected = (QAbstractButton, QAbstractItemView, QAbstractSlider, QAbstractSpinBox,
                     QComboBox, QLabel, QLineEdit, QMenu, QMenuBar, QPlainTextEdit, QTextEdit)
        while widget and widget is not self.host:
            if isinstance(widget, protected):
                return False
            widget = widget.parentWidget()
        return widget is self.host

    def _start_move(self, event):
        handle = self.host.windowHandle()
        if handle and handle.startSystemMove():
            return True
        if not self.host.isMaximized():
            self._drag_offset = event.globalPosition().toPoint() - self.host.frameGeometry().topLeft()
            return True
        return False

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind not in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
            return False
        if not isinstance(watched, QWidget) or watched.window() is not self.host:
            return False
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            dragging = self._drag_offset is not None
            self._drag_offset = None
            return dragging
        if kind == QEvent.Type.MouseMove and self._drag_offset is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self.host.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
            self._drag_offset = None
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton and self._is_background(watched):
            if not self.host.isMaximized():
                point = watched.mapTo(self.host, event.position().toPoint())
                edges = Qt.Edge(0)
                if point.x() < 12: edges |= Qt.Edge.LeftEdge
                if point.x() >= self.host.width() - 12: edges |= Qt.Edge.RightEdge
                if point.y() < 12: edges |= Qt.Edge.TopEdge
                if point.y() >= self.host.height() - 12: edges |= Qt.Edge.BottomEdge
                if edges and self.host.windowHandle():
                    if self.host.windowHandle().startSystemResize(edges):
                        return True
            return self._start_move(event)
        return super().eventFilter(watched, event)
