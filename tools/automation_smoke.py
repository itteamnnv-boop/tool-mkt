"""Offline multi-platform publishing checks; no credentials or network access."""
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app import config
from app.core import automation_publisher as publisher, social_tokens
from app.ui.automation_settings_dialog import AutomationSettingsTab
from app.ui.automation_tab import AutomationTab


class PublishingChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.settings = deepcopy(config.DEFAULT_SETTINGS)
        self.settings.update(automation_attachment="video", automation_platforms=["facebook", "tiktok", "youtube"],
                             automation_facebook_page_ids=["one"])
        self.pages = [{"id": "one", "name": "Demo Page", "token": "demo"}]
        self.stack.enter_context(patch.object(config, "load_settings", side_effect=lambda: deepcopy(self.settings)))
        self.stack.enter_context(patch.object(config, "save_settings", side_effect=self.settings.update))
        self.stack.enter_context(patch.object(config, "list_pages", return_value=self.pages))
        self.stack.enter_context(patch.object(config, "get_page_token", return_value="demo"))
        self.stack.enter_context(patch.object(config, "get_secret", return_value=""))
        self.stack.enter_context(patch.object(config, "get_tiktok_account", return_value={"access_token": "demo"}))
        self.stack.enter_context(patch.object(config, "get_youtube_account", return_value={"access_token": "demo"}))
        self.stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("Live API call")))
        self.stack.enter_context(patch.object(publisher, "ensure_tiktok_token", return_value="demo"))
        self.stack.enter_context(patch.object(publisher, "ensure_youtube_token", return_value="demo"))
        self.facebook = self.stack.enter_context(patch.object(publisher, "post_to_pages", return_value=[
            {"id": "one", "name": "Demo Page", "ok": True, "post_id": "fb-post"}]))
        self.tiktok = self.stack.enter_context(patch.object(publisher, "TikTokClient")).return_value
        self.tiktok.query_creator_info.return_value = {"privacy_level_options": ["SELF_ONLY"], "comment_disabled": True}
        self.tiktok.post_video.return_value = {"publish_id": "tt-post"}
        self.youtube = self.stack.enter_context(patch.object(publisher, "YouTubeClient")).return_value
        self.youtube.upload_video.return_value = {"id": "yt-post"}
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.video = Path(directory) / "demo.mp4"
        self.video.write_bytes(b"offline-fixture")

    def publish(self, **kwargs):
        return publisher.publish_generated(self.settings, "Demo caption", "Demo topic", self.pages,
                                           video_path=self.video, **kwargs)

    def test_all_platforms_and_saved_metadata(self):
        self.settings.update(automation_youtube_title="Saved title", automation_youtube_tags="one, two")
        publisher.validate_destinations(self.settings, self.pages)
        results = self.publish(scheduled_time=123456)
        self.assertEqual([r["post_id"] for r in results], ["fb-post", "tt-post", "yt-post"])
        self.assertTrue(all(r["ok"] for r in results))
        self.assertEqual(self.facebook.call_args.kwargs["scheduled_time"], 123456)
        self.assertEqual(self.tiktok.post_video.call_args.kwargs["privacy_level"], "SELF_ONLY")
        self.assertTrue(self.tiktok.post_video.call_args.kwargs["disable_comment"])
        self.assertEqual(self.youtube.upload_video.call_args.kwargs["title"], "Saved title")
        self.assertEqual(self.youtube.upload_video.call_args.kwargs["tags"], ["one", "two"])
        self.assertEqual(self.youtube.upload_video.call_args.kwargs["privacy_status"], "private")

    def test_failure_does_not_block_other_platforms(self):
        self.tiktok.post_video.side_effect = RuntimeError("TikTok rejected")
        results = self.publish()
        self.assertEqual([r["ok"] for r in results], [True, False, True])
        self.assertIn("TikTok rejected", results[1]["error"])

    def test_successful_targets_are_not_reposted(self):
        self.assertEqual(self.publish(skip_targets={"facebook:one", "tiktok", "youtube"}), [])
        self.facebook.assert_not_called()
        self.tiktok.post_video.assert_not_called()
        self.youtube.upload_video.assert_not_called()

    def test_invalid_privacy_does_not_upload_tiktok(self):
        self.settings["automation_tiktok_privacy"] = "PUBLIC_TO_EVERYONE"
        results = self.publish()
        self.assertFalse(results[1]["ok"])
        self.tiktok.post_video.assert_not_called()
        self.youtube.upload_video.assert_called_once()

    def test_invalid_targets_and_missing_video(self):
        for changes in ({"automation_platforms": []}, {"automation_attachment": "image"}):
            with self.assertRaises(ValueError):
                publisher.validate_destinations({**self.settings, **changes}, self.pages)
        with self.assertRaises(ValueError):
            publisher.validate_destinations(self.settings, [])
        self.video.unlink()
        with self.assertRaises(ValueError):
            self.publish()
        self.facebook.assert_not_called()

    def test_youtube_only_needs_no_facebook_pages(self):
        self.settings["automation_platforms"] = ["youtube"]
        publisher.validate_destinations(self.settings, [])
        results = publisher.publish_generated(self.settings, "caption", "x" * 120, [], video_path=self.video)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(self.youtube.upload_video.call_args.kwargs["title"]), 100)
        self.facebook.assert_not_called()

    def test_facebook_text_and_photo_attachments(self):
        for attachment in ("none", "image"):
            settings = {**self.settings, "automation_platforms": ["facebook"], "automation_attachment": attachment}
            publisher.validate_destinations(settings, self.pages)
            results = publisher.publish_generated(settings, "caption", "topic", self.pages, image_path=self.video)
            self.assertEqual(results[0]["post_type"], "text" if attachment == "none" else "photo")
            self.assertIn("message" if attachment == "none" else "caption", self.facebook.call_args.kwargs)

    def test_disconnected_account_stops_before_generation(self):
        self.settings.update(automation_auto_post=True, heygen_avatar_id="avatar", heygen_voice_id="voice")
        tab = AutomationTab()
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.processing_dialog.close)
        tab.idea_input.setPlainText("Demo idea")
        with patch.object(config, "get_tiktok_account", return_value={}), \
             patch("app.ui.automation_tab.get_text_client") as text_client:
            tab._on_run_pipeline()
            text_client.assert_not_called()
        self.assertTrue(tab.run_btn.isEnabled())
        self.facebook.assert_not_called()

    def test_full_automatic_video_pipeline_offline(self):
        self.settings.update(automation_auto_post=True, heygen_avatar_id="avatar", heygen_voice_id="voice")
        tab = AutomationTab()
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.processing_dialog.close)
        tab.idea_input.setPlainText("Demo idea")
        client = Mock()
        client.generate_post.return_value = "Generated caption"
        client.suggest_video_script.return_value = "Video script"
        with patch("app.ui.automation_tab.get_text_client", return_value=client), \
             patch("app.ui.automation_tab.HeyGenClient") as heygen, \
             patch("app.ui.automation_tab.history_store.add_content"), \
             patch("app.ui.automation_tab.history_store.add_video"), \
             patch("app.ui.automation_tab.history_store.add_post") as history, \
             patch("app.ui.automation_tab.QMessageBox.question") as confirmation:
            heygen.return_value.generate_and_wait.return_value = self.video
            tab._on_run_pipeline()
            for _ in range(100):
                QTest.qWait(20)
                if tab._published_targets == {"facebook:one", "tiktok", "youtube"}:
                    break
            self.assertEqual(tab._published_targets, {"facebook:one", "tiktok", "youtube"})
            self.assertEqual(history.call_count, 3)
            confirmation.assert_not_called()
            self.assertTrue(tab.run_btn.isEnabled())
            self.assertFalse(tab.processing_dialog.isVisible())
            self.assertEqual(self.youtube.upload_video.call_args.kwargs["title"], "Demo idea")
            tab._worker.wait(1000)

    def test_settings_save_restore_and_validation(self):
        panel = AutomationSettingsTab()
        self.addCleanup(panel.deleteLater)
        panel.youtube_title_input.setText("Saved video title")
        panel.auto_post_check.setChecked(True)
        panel._on_save()
        restored = AutomationSettingsTab()
        self.addCleanup(restored.deleteLater)
        self.assertTrue(all(check.isChecked() for check in restored.platform_checks.values()))
        self.assertTrue(restored.page_checks["one"].isChecked())
        self.assertEqual(restored.youtube_title_input.text(), "Saved video title")
        self.assertTrue(restored.auto_post_check.isChecked())
        panel.attachment_combo.setCurrentIndex(panel.attachment_combo.findData("image"))
        panel._on_save()
        self.assertEqual(self.settings["automation_attachment"], "video")

    def test_auto_post_uses_snapshot_and_unlocks_after_results(self):
        tab = AutomationTab()
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.processing_dialog.close)
        tab._run_settings = {**deepcopy(self.settings), "automation_auto_post": True}
        tab._run_pages = self.pages
        tab._run_topic = "Original topic"
        tab._video_path = self.video
        tab.review_text.setPlainText("caption")
        self.settings.update(automation_auto_post=False, automation_platforms=["facebook"])
        with patch("app.ui.automation_tab.Worker") as worker, patch("app.ui.automation_tab.QMessageBox.question") as confirm:
            tab._finish_pipeline()
            worker.assert_called_once()
            confirm.assert_not_called()
            self.assertEqual(worker.call_args.kwargs["settings"]["automation_platforms"], ["facebook", "tiktok", "youtube"])
            self.assertFalse(tab.run_btn.isEnabled())
            self.assertFalse(tab.post_btn.isEnabled())
            self.assertTrue(tab.review_text.isReadOnly())
        results = publisher.publish_generated(tab._run_settings, "caption", tab._run_topic,
                                             tab._run_pages, video_path=self.video)
        with patch("app.ui.automation_tab.history_store.add_post") as history:
            tab._on_post_done("caption", "", results)
            self.assertEqual(history.call_count, 3)
        self.assertTrue(tab.run_btn.isEnabled())
        self.assertFalse(tab.review_text.isReadOnly())
        self.assertEqual(tab._published_targets, {"facebook:one", "tiktok", "youtube"})

    def test_preflight_failure_finishes_processing(self):
        tab = AutomationTab()
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.processing_dialog.close)
        tab._run_settings = deepcopy(self.settings)
        tab._run_pages = []
        tab.run_btn.setEnabled(False)
        tab._on_post(auto=True)
        self.assertTrue(tab.run_btn.isEnabled())
        self.assertFalse(tab.processing_dialog.isVisible())
        self.assertTrue(tab.result_label.text())

    def test_shared_token_refresh_preserves_accounts(self):
        for platform in ("tiktok", "youtube"):
            account = {"access_token": "old", "refresh_token": "refresh", "token_expires_at": 0,
                       "display_name": "Creator", "channel_title": "Channel"}
            settings = {"tiktok_client_key": "key", "youtube_client_id": "id"}
            with patch.object(config, f"get_{platform}_account", return_value=account), \
                 patch.object(config, "get_secret", return_value="secret"), \
                 patch.object(config, "load_settings", return_value=settings), \
                 patch.object(config, f"save_{platform}_account") as save, \
                 patch.object(social_tokens, f"refresh_{platform}", return_value={"access_token": "new", "expires_at": 9999999999}):
                token = getattr(social_tokens, f"ensure_{platform}_token")()
                self.assertEqual(token, "new")
                self.assertEqual(save.call_args.kwargs["access_token"], "new")


if __name__ == "__main__":
    unittest.main(verbosity=2)
