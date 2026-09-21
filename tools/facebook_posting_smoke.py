"""Posting regression tests. All external requests and credentials are mocked."""
import os
import sys
import time
import unittest
import requests
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import QApplication, QMessageBox
from app import config
from app.core.facebook_client import FacebookClient, post_to_pages
from app.core.facebook_schedule import status_label
from app.ui.facebook_tab import FacebookTab
from app.ui.automation_tab import AutomationTab


class PostingChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(config, "load_settings", return_value=dict(config.DEFAULT_SETTINGS)))
        self.stack.enter_context(patch.object(config, "get_secret", return_value=""))
        self.stack.enter_context(patch.object(config, "list_pages", return_value=[]))
        self.stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("Live network")))
        self.pages = [dict(id="123", name="Demo", token="fake")]
        folder = self.stack.enter_context(TemporaryDirectory())
        self.media = Path(folder) / "test.mp4"
        self.media.write_bytes(b"synthetic")

    def tab(self, cls=FacebookTab):
        tab = cls()
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.processing_dialog.close)
        self.stack.enter_context(patch.object(tab.pages_selector, "selected_pages", return_value=self.pages))
        return tab

    def test_missing_remote_id_is_not_success(self):
        with patch.object(FacebookClient, "post_text", return_value={}):
            result = post_to_pages(self.pages, "text", message="Caption")[0]
            self.assertFalse(result["ok"])
            self.assertTrue(result["uncertain"])

    def test_timeout_is_uncertain_and_token_is_redacted(self):
        with patch.object(FacebookClient, "post_text", side_effect=requests.Timeout("timeout access_token=fake")):
            result = post_to_pages(self.pages, "text", message="Caption")[0]
        self.assertTrue(result["uncertain"])
        self.assertNotIn("access_token=fake", result["error"])
        self.assertEqual(status_label(dict(ok=False, schedule_status='{"uncertain": true}')),
                         "Chưa xác nhận — kiểm tra Page")

    def test_auto_retry_skips_uncertain_result(self):
        tab = self.tab(AutomationTab)
        tab._on_post_done("caption", "", [dict(ok=False, uncertain=True, name="Demo", target="facebook:123",
                                              platform="facebook", error="Check Page")])
        self.assertIn("facebook:123", tab._published_targets)

    def test_album_upload_does_not_send_expired_schedule(self):
        reply = Mock(ok=True)
        reply.json.return_value = {"id": "photo"}
        with patch("app.core.facebook_client.time.time", side_effect=[1000, 1601]), \
             patch("app.core.facebook_client.requests.post", return_value=reply) as api:
            with self.assertRaises(ValueError):
                FacebookClient("123", "fake").post_photos([self.media], "Caption", 2200)
            self.assertEqual(api.call_count, 1)
            self.assertTrue(api.call_args.args[0].endswith("/photos"))

    def test_rejected_page_does_not_hide_successful_page(self):
        other = dict(id="456", name="Other", token="other-token")
        with patch.object(FacebookClient, "post_text", side_effect=[{"id": "123_1"}, RuntimeError("Permission denied")]):
            results = post_to_pages(self.pages + [other], "text", message="Caption")
        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[1]["ok"])
        self.assertFalse(results[1]["uncertain"])

    def test_invalid_schedule_never_calls_api(self):
        for timestamp in (0, int(time.time()) - 60, int(time.time()) + 30):
            with self.subTest(timestamp=timestamp), patch("app.core.facebook_client.requests.post") as api:
                with self.assertRaises(ValueError):
                    FacebookClient("123", "fake").post_text("Caption", scheduled_time=timestamp)
                api.assert_not_called()

    def test_manual_link_only_post(self):
        tab = self.tab()
        tab.link_input.setText("https://example.com/article")
        with patch("app.ui.facebook_tab.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
             patch("app.ui.facebook_tab.Worker") as worker:
            tab._on_post()
            worker.assert_called_once()
            self.assertEqual(worker.call_args.kwargs["link"], "https://example.com/article")

    def test_post_locks_editor_and_reentrant_call(self):
        tab = self.tab()
        tab.message_input.setPlainText("Caption")
        with patch("app.ui.facebook_tab.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
             patch("app.ui.facebook_tab.Worker") as worker:
            tab._on_post()
            self.assertTrue(tab.message_input.isReadOnly())
            self.assertFalse(tab.schedule_check.isEnabled())
            tab._on_post()
            self.assertEqual(worker.call_count, 1)
            tab._on_error("Simulated failure")
            self.assertFalse(tab.message_input.isReadOnly())
            self.assertTrue(tab.post_btn.isEnabled())

    def test_auto_post_respects_schedule(self):
        tab = self.tab(AutomationTab)
        tab._run_settings = dict(config.DEFAULT_SETTINGS, automation_platforms=["facebook"],
                                 automation_attachment="none", automation_auto_post=True)
        tab._run_pages = self.pages
        tab.review_text.setPlainText("Caption")
        tab.schedule_check.setChecked(True)
        when = QDateTime.currentDateTime().addSecs(3600)
        tab.schedule_datetime.setDateTime(when)
        with patch("app.ui.automation_tab.Worker") as worker:
            tab._on_post(auto=True)
            self.assertEqual(worker.call_args.kwargs["scheduled_time"], when.toSecsSinceEpoch())

    def test_all_media_payloads(self):
        client = FacebookClient("123", "fake")
        for scheduled in (None, int(time.time()) + 3600):
            for kind in ("text", "photo", "video"):
                response = Mock(ok=True)
                response.json.return_value = {"id": "123_456"}
                with self.subTest(kind=kind, scheduled=scheduled), patch("app.core.facebook_client.requests.post", return_value=response) as api:
                    if kind == "text":
                        client.post_text("Caption", scheduled_time=scheduled)
                    elif kind == "photo":
                        client.post_photo(self.media, "Caption", scheduled_time=scheduled)
                    else:
                        client.post_video(self.media, "Caption", scheduled_time=scheduled)
                    data = api.call_args.kwargs["data"]
                    if scheduled:
                        self.assertEqual(data["published"], "false")
                        self.assertEqual(data["scheduled_publish_time"], scheduled)
                    else:
                        self.assertNotIn("scheduled_publish_time", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
