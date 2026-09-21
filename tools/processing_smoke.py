"""Offline checks and preview images for the 2D task progress dialog."""
import os
import sys
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import config
from app.ui.content_tab import ContentTab
from app.ui.widgets.processing_dialog import ProcessingDialog
from app.ui.widgets.process_scene import ProcessScene
from app.ui.theme import apply_theme
from app.workers.async_worker import Worker


class ProcessingChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(config, "get_secret", return_value=""))
        self.stack.enter_context(patch.object(config, "load_settings", return_value=dict(config.DEFAULT_SETTINGS)))
        self.stack.enter_context(patch.object(config, "save_settings"))
        self.stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("Live API call")))
        apply_theme(self.app)

    def wait(self, condition):
        for _ in range(150):
            QTest.qWait(20)
            if condition():
                return
        self.fail("Task dialog did not reach the expected state")

    def dialog(self):
        dialog = ProcessingDialog()
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        return dialog

    def test_animation_does_not_invent_completed_steps(self):
        dialog = self.dialog()
        dialog.start("Working")
        QTest.qWait(30)
        before = dialog.scene.grab().toImage()
        QTest.qWait(150)
        self.assertNotEqual(before, dialog.scene.grab().toImage())
        self.assertEqual(dialog.scene.states, {"start": "done", "process": "active", "result": "waiting"})
        self.assertEqual(dialog.progress_bar.maximum(), 0)
        dialog.finish("Done")
        self.assertFalse(dialog.scene.timer.isActive())
        self.assertTrue(all(state == "done" for state in dialog.scene.states.values()))

    def test_hidden_scene_pauses_animation_and_keeps_task_state(self):
        dialog = self.dialog()
        dialog.start("Working")
        self.assertTrue(dialog.scene.timer.isActive())
        dialog.hide_btn.click()
        self.assertFalse(dialog.isVisible())
        self.assertFalse(dialog.scene.timer.isActive())
        self.assertTrue(dialog.scene.running)
        dialog.set_status("Real updated status")
        self.assertFalse(dialog.isVisible())
        self.assertEqual(dialog.status_label.text(), "Real updated status")
        dialog.show()
        self.assertTrue(dialog.scene.timer.isActive())
        dialog.finish()

    def test_worker_progress_and_completion(self):
        dialog = self.dialog()
        release = threading.Event()
        self.addCleanup(release.set)
        def task(on_progress=None):
            on_progress("Real provider status")
            release.wait(2)
            return "result"
        worker = Worker(task)
        dialog.track(worker, "Starting task")
        self.assertTrue(dialog.isVisible())
        worker.start()
        self.wait(lambda: dialog.status_label.text() == "Real provider status")
        self.assertEqual(dialog.scene.states["result"], "waiting")
        release.set()
        self.wait(lambda: not dialog.scene.running)
        worker.wait(1000)
        self.assertFalse(dialog.isVisible())
        self.assertEqual(dialog.scene.states["result"], "done")

    def test_errors_and_cancellation_stop_simulation(self):
        for cancelled in (False, True):
            dialog = self.dialog()
            def task():
                error = RuntimeError("Provider error")
                error.is_cancelled = cancelled
                raise error
            worker = Worker(task)
            dialog.track(worker, "Starting")
            with patch("app.workers.async_worker.traceback.print_exc"):
                worker.start()
                self.wait(lambda: not dialog.scene.running)
                worker.wait(1000)
            self.assertEqual(dialog.scene.states["process"], "cancelled" if cancelled else "error")
            self.assertEqual(dialog.scene.states["result"], "waiting")
            self.assertFalse(dialog.scene.timer.isActive())

    def test_partial_post_failures_are_not_shown_as_success(self):
        dialog = self.dialog()
        worker = Worker(lambda: [{"ok": True}, {"ok": False}])
        dialog.track(worker, "Posting")
        worker.start()
        self.wait(lambda: not dialog.scene.running)
        worker.wait(1000)
        self.assertEqual(dialog.scene.states["process"], "error")

    def test_real_platform_events_preserve_prior_errors(self):
        dialog = self.dialog()
        stages = [(key, key.title(), key) for key in ("facebook", "tiktok", "youtube")]
        dialog.start("Posting", stages=stages)
        dialog.set_stage("facebook", "done")
        dialog.set_stage("tiktok", "active")
        dialog.set_stage("tiktok", "error")
        dialog.set_stage("youtube", "active")
        dialog.set_stage("youtube", "done")
        dialog.finish("Partial failure", outcome="error")
        self.assertEqual(dialog.scene.states, {"facebook": "done", "tiktok": "error", "youtube": "done"})

    def test_content_generation_opens_dialog_after_validation(self):
        tab = ContentTab()
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.processing_dialog.close)
        client = Mock()
        release = threading.Event()
        self.addCleanup(release.set)
        def generate(**kwargs):
            release.wait(2)
            return "Generated content"
        client.generate_post.side_effect = generate
        with patch("app.ui.content_tab.get_text_client", return_value=client), \
             patch("app.ui.content_tab.history_store.add_content"):
            tab._on_generate()
            self.assertFalse(tab.processing_dialog.isVisible())
            tab.topic_input.setText("Demo topic")
            tab._on_generate()
            self.assertTrue(tab.processing_dialog.isVisible())
            release.set()
            self.wait(lambda: not tab._generating)
            self.wait(lambda: not tab.processing_dialog.scene.running)
            tab._worker.wait(1000)
        self.assertEqual(tab.result_text.toPlainText(), "Generated content")

    def test_dark_and_light_preview_layouts(self):
        output = ROOT / "output" / "ui-review"
        output.mkdir(parents=True, exist_ok=True)
        stages = [("content", "Viết content", "content"), ("asset", "Tạo video", "video"),
                  ("facebook", "Đăng Facebook", "facebook"), ("tiktok", "Đăng TikTok", "tiktok"),
                  ("youtube", "Đăng YouTube", "youtube")]
        for tint in ("black", "light"):
            apply_theme(self.app, {"glass_tint": tint, "glass_transparency": 0})
            dialog = self.dialog()
            dialog.start("Đang tạo video, chờ phản hồi từ nhà cung cấp...", stages=stages)
            dialog.set_stage("content", "done")
            dialog.set_stage("asset")
            QTest.qWait(50)
            self.assertLessEqual(dialog.width(), 760)
            self.assertGreaterEqual(dialog.scene.width(), 500)
            self.assertTrue(dialog.grab().save(str(output / f"processing-2d-{tint}.png")))
            dialog.finish()


if __name__ == "__main__":
    unittest.main(verbosity=2)
