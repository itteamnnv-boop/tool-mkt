"""Progress minimize/restore lifecycle, including a real background worker."""
import os
from pathlib import Path
import sys
import threading
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from app.ui.widgets.processing_dialog import ProcessingDialog
from app.ui.widgets.task_indicator import TaskIndicator
from app.workers.async_worker import Worker


class ProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.parent = QWidget()
        self.parent.show()
        self.dialog = ProcessingDialog(self.parent)
        self.button = TaskIndicator(self.parent)
        self.button.register("Tạo ảnh", self.dialog)

    def tearDown(self):
        self.dialog.finish()
        self.dialog.reject()
        self.parent.close()
        self.parent.deleteLater()
        self.app.processEvents()

    def test_close_escape_and_button_minimize_without_resetting(self):
        self.assertTrue(self.button.isHidden())
        self.dialog.start("Generating")
        QTest.qWait(30)
        for hide in (self.dialog.close, lambda: QTest.keyClick(self.dialog, Qt.Key.Key_Escape), self.dialog.hide_btn.click):
            before = self.dialog.clock.elapsed()
            hide()
            self.assertFalse(self.dialog.isVisible())
            self.assertTrue(self.dialog.scene.running)
            self.assertTrue(self.dialog.elapsed_timer.isActive())
            self.assertFalse(self.button.isHidden())
            self.button.click()
            self.assertTrue(self.dialog.isVisible())
            self.assertGreaterEqual(self.dialog.clock.elapsed(), before)

    def test_worker_finishes_while_minimized_and_result_can_be_reopened(self):
        release = threading.Event()
        def work(on_progress=None):
            release.wait(3)
            on_progress("Upload complete")
            return "result"
        worker = Worker(work)
        try:
            self.dialog.track(worker, "Uploading")
            worker.start()
            self.dialog.close()
            release.set()
            for _ in range(100):
                QTest.qWait(10)
                if not self.dialog.scene.running:
                    break
            self.assertFalse(self.dialog.scene.running)
            self.assertFalse(self.dialog.isVisible())
            self.assertFalse(self.button.isHidden())
            self.button.click()
            self.assertTrue(self.dialog.isVisible())
            self.assertEqual(self.dialog.status_label.text(), "Tác vụ hoàn tất.")
            self.assertEqual(self.dialog.progress_bar.value(), 1)
            self.dialog.close()
            self.assertTrue(self.button.isHidden())
        finally:
            release.set()
            worker.wait(4000)

    def test_multiple_tasks_menu_and_error_result(self):
        other = ProcessingDialog(self.parent)
        self.button.register("Video", other)
        self.dialog.start("Image")
        other.start("Video")
        self.dialog.close()
        other.close()
        self.assertEqual(self.button.text(), "2")
        self.button.click()
        self.assertEqual(len(self.button._menu.actions()), 2)
        self.button._menu.actions()[1].trigger()
        self.button._menu.hide()
        self.assertTrue(other.isVisible())
        self.assertFalse(self.dialog.isVisible())
        other.finish("Lỗi: Network", outcome="error")
        self.assertIn("Lỗi: Network", self.button.toolTip())
        other.restore()
        self.assertEqual(other.status_label.text(), "Lỗi: Network")
        other.reject()
        self.assertEqual(self.button.text(), "1")

    def test_new_run_reuses_single_indicator(self):
        self.dialog.start("First")
        self.dialog.finish()
        self.dialog.start("Second")
        self.assertEqual(self.button.text(), "1")
        self.assertEqual(self.dialog.hide_btn.text(), "Thu gọn")
        self.assertTrue(self.dialog.scene.running)


if __name__ == "__main__":
    unittest.main()
