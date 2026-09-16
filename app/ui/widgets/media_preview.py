"""Aspect-ratio-preserving preview that does not force a layout wider than its card."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy


class MediaPreview(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._original = QPixmap()
        self.setObjectName("mediaPreview")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

    def setPixmap(self, pixmap: QPixmap) -> None:
        self._original = QPixmap(pixmap)
        self._fit_image()

    def setText(self, text: str) -> None:
        self._original = QPixmap()
        super().setText(text)

    def clear(self) -> None:
        self._original = QPixmap()
        super().clear()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_image()

    def _fit_image(self) -> None:
        if not self._original.isNull():
            super().setPixmap(self._original.scaled(
                max(1, self.width() - 24), max(1, self.height() - 24),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))
