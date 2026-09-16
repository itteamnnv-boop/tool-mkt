"""Small, non-blocking notifications used by the main window."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class Toast(QFrame):
    """A single reusable toast that is positioned by its owning window."""

    _ICONS = {"success": "✓", "error": "!", "info": "…"}
    _TITLES = {"success": "Hoàn tất", "error": "Có lỗi", "info": "Đang xử lý"}

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(320)
        self.setMaximumWidth(460)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 10, 12)
        layout.setSpacing(10)
        self.icon = QLabel()
        self.icon.setObjectName("toastIcon")
        self.title = QLabel()
        self.title.setObjectName("toastTitle")
        self.message = QLabel()
        self.message.setObjectName("toastMessage")
        self.message.setWordWrap(True)
        text = QWidget()
        text_layout = QHBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.addWidget(self.title)
        text_layout.addSpacing(8)
        text_layout.addWidget(self.message, 1)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("toastClose")
        self.close_button.setFixedSize(22, 22)
        self.close_button.clicked.connect(self.hide)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(text, 1)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, message: str, level: str = "info") -> None:
        level = level if level in self._ICONS else "info"
        self.setProperty("level", level)
        self.style().unpolish(self)
        self.style().polish(self)
        self.icon.setText(self._ICONS[level])
        self.title.setText(self._TITLES[level])
        self.message.setText(message)
        self.adjustSize()
        parent = self.parentWidget()
        if parent:
            self.move(max(12, parent.width() - self.width() - 28), 28)
        self.raise_()
        self.show()
        self._timer.start(7000 if level == "error" else 4200 if level == "success" else 3200)
