"""Offline checks for dragging empty backgrounds without intercepting controls."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QPushButton, QTextEdit, QWidget
from app.ui.widgets.glass_chrome import GlassTitleBar


class WindowDragChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.host = QWidget()
        self.host.resize(600, 400)
        self.host.move(100, 100)
        self.background = QWidget(self.host)
        self.background.setGeometry(20, 50, 560, 330)
        self.chrome = GlassTitleBar(self.host)
        self.chrome.resize(600, 32)
        self.host.show()
        self.app.processEvents()
        self.addCleanup(self.host.deleteLater)
        self.addCleanup(self.host.close)
        self.addCleanup(lambda: self.app.removeEventFilter(self.chrome))

    @staticmethod
    def mouse(kind, local, global_point, button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton):
        return QMouseEvent(kind, QPointF(local), QPointF(global_point), button, buttons, Qt.KeyboardModifier.NoModifier)

    def test_empty_background_starts_native_window_move(self):
        with patch.object(QWindow, "startSystemMove", return_value=True) as move:
            QTest.mouseClick(self.background, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
            move.assert_called_once()

    def test_manual_fallback_moves_window_and_releases(self):
        start = self.host.pos()
        global_point = self.background.mapToGlobal(QPoint(100, 100))
        with patch.object(QWindow, "startSystemMove", return_value=False):
            QApplication.sendEvent(self.background, self.mouse(QEvent.Type.MouseButtonPress, QPoint(100, 100), global_point))
            QApplication.sendEvent(self.background, self.mouse(QEvent.Type.MouseMove, QPoint(140, 130), global_point + QPoint(40, 30), button=Qt.MouseButton.NoButton))
            self.assertEqual(self.host.pos(), start + QPoint(40, 30))
            QApplication.sendEvent(self.background, self.mouse(QEvent.Type.MouseButtonRelease, QPoint(140, 130), global_point + QPoint(40, 30), buttons=Qt.MouseButton.NoButton))
            self.assertIsNone(self.chrome._drag_offset)

    def test_buttons_still_click_without_moving(self):
        button = QPushButton("Action", self.background)
        button.setGeometry(60, 60, 100, 32)
        button.show()
        clicks = []
        button.clicked.connect(lambda: clicks.append(True))
        with patch.object(QWindow, "startSystemMove", return_value=True) as move:
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            move.assert_not_called()
        self.assertEqual(clicks, [True])

    def test_inputs_and_editor_viewports_keep_normal_mouse_behavior(self):
        line = QLineEdit("Editable", self.background)
        line.setGeometry(50, 50, 180, 32)
        editor = QTextEdit(self.background)
        editor.setGeometry(50, 100, 200, 100)
        line.show()
        editor.show()
        with patch.object(QWindow, "startSystemMove", return_value=True) as move:
            QTest.mouseClick(line, Qt.MouseButton.LeftButton)
            QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
            move.assert_not_called()
        self.assertFalse(self.chrome._is_background(editor.viewport()))

    def test_other_dialogs_do_not_drag_main_window(self):
        dialog = QDialog(self.host)
        dialog.resize(200, 100)
        dialog.show()
        with patch.object(QWindow, "startSystemMove", return_value=True) as move:
            QTest.mouseClick(dialog, Qt.MouseButton.LeftButton, pos=QPoint(50, 50))
            move.assert_not_called()
        dialog.close()

    def test_edge_resize_still_has_priority(self):
        with patch.object(QWindow, "startSystemResize", return_value=True) as resize, \
             patch.object(QWindow, "startSystemMove", return_value=True) as move:
            QTest.mouseClick(self.host, Qt.MouseButton.LeftButton, pos=QPoint(2, 200))
            resize.assert_called_once_with(Qt.Edge.LeftEdge)
            move.assert_not_called()

    def test_right_click_does_not_start_drag(self):
        with patch.object(QWindow, "startSystemMove", return_value=True) as move:
            QTest.mouseClick(self.background, Qt.MouseButton.RightButton, pos=QPoint(100, 100))
            move.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
