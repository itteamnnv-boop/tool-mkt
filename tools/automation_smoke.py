"""Offline multi-platform publishing checks; no credentials or network access."""
import os
import sys
import tempfile
import unittest
import json
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
from app.core.facebook_client import FacebookClient
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
        events = []
        results = self.publish(on_stage=lambda key, state: events.append((key, state)))
        self.assertEqual([r["ok"] for r in results], [True, False, True])
        self.assertIn("TikTok rejected", results[1]["error"])
        self.assertEqual(events, [("facebook", "active"), ("facebook", "done"),
                                  ("tiktok", "active"), ("tiktok", "error"),
                                  ("youtube", "active"), ("youtube", "done")])

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
             patch("app.storage.history_store.save_post") as history, \
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
            self.assertEqual(tab.processing_dialog.scene.states,
                             {"content": "done", "asset": "done", "facebook": "done", "tiktok": "done", "youtube": "done"})
            self.assertEqual(self.youtube.upload_video.call_args.kwargs["title"], "Demo idea")
            tab._worker.wait(1000)

    def test_image_count_setting_roundtrip(self):
        self.settings.update(automation_platforms=["facebook"], automation_attachment="image")
        panel = AutomationSettingsTab()
        self.addCleanup(panel.deleteLater)
        self.assertEqual(panel.image_count_spin.value(), 1)
        panel.image_count_spin.setValue(3)
        panel._on_save()
        restored = AutomationSettingsTab()
        self.addCleanup(restored.deleteLater)
        self.assertEqual(restored.image_count_spin.value(), 3)
        self.assertTrue(restored.image_count_spin.isEnabled())
        restored.attachment_combo.setCurrentIndex(restored.attachment_combo.findData("video"))
        self.assertFalse(restored.image_count_spin.isEnabled())

    def test_multiple_images_pipeline_and_partial_failure(self):
        from PySide6.QtGui import QPixmap, QColor
        self.settings.update(automation_platforms=["facebook"], automation_attachment="image",
                             automation_image_count=3, automation_auto_post=True)
        paths = []
        for i in range(3):
            path = self.video.parent / f"image-{i}.png"
            pixmap = QPixmap(40, 40)
            pixmap.fill(QColor('blue'))
            pixmap.save(str(path))
            paths.append(path)
        for fail in (False, True):
            self.facebook.reset_mock()
            tab = AutomationTab()
            self.addCleanup(tab.deleteLater)
            self.addCleanup(tab.processing_dialog.close)
            tab.idea_input.setPlainText('Three-image post')
            client = Mock()
            client.generate_post.return_value = 'Caption'
            client.suggest_image_prompt.return_value = 'Garden'
            with patch('app.ui.automation_tab.get_text_client', return_value=client), \
                 patch('app.ui.automation_tab.ImageClient') as image_client, \
                 patch('app.ui.automation_tab.history_store.add_content'), \
                 patch('app.ui.automation_tab.history_store.add_image') as saved, \
                 patch('app.storage.history_store.save_post'):
                image_client.return_value.generate_image.side_effect = [paths[0], RuntimeError('Image failed')] if fail else paths
                tab._on_run_pipeline()
                for _ in range(150):
                    QTest.qWait(20)
                    if tab.run_btn.isEnabled():
                        break
                self.assertTrue(tab.run_btn.isEnabled())
                if fail:
                    self.facebook.assert_not_called()
                    self.assertEqual(saved.call_count, 1)
                    self.assertFalse(tab.post_btn.isEnabled())
                else:
                    self.assertEqual(tab._image_paths, paths)
                    self.assertEqual(tab.image_selector.count(), 3)
                    self.assertEqual(saved.call_count, 3)
                    self.assertEqual(self.facebook.call_args.args[1], 'photos')
                    self.assertEqual(self.facebook.call_args.kwargs['image_paths'], paths)
                    self.assertEqual(tab._published_targets, {'facebook:one'})
                tab._worker.wait(1000)

    def test_multi_photo_upload_then_single_feed_and_schedule(self):
        paths = [self.video, self.video.parent / 'second.png']
        paths[1].write_bytes(b'image')
        replies = [Mock(ok=True), Mock(ok=True), Mock(ok=True)]
        for response, identity in zip(replies, ('photo-1', 'photo-2', 'post-1')):
            response.json.return_value = {'id': identity}
        with patch('app.core.facebook_client.requests.post', side_effect=replies) as post:
            import time
            scheduled = int(time.time()) + 3600
            result = FacebookClient('page', 'token').post_photos(paths, 'Caption', scheduled)
            self.assertEqual(result['id'], 'post-1')
            self.assertEqual(post.call_count, 3)
            self.assertEqual(post.call_args_list[0].kwargs['data']['published'], 'false')
            final = post.call_args.kwargs['data']
            self.assertEqual(final['scheduled_publish_time'], scheduled)
            self.assertEqual(final['message'], 'Caption')
            self.assertEqual(json.loads(final['attached_media']), [{'media_fbid': 'photo-1'}, {'media_fbid': 'photo-2'}])
        with patch('app.core.facebook_client.requests.post', side_effect=[replies[0], RuntimeError('Upload failed')]) as post:
            with self.assertRaises(RuntimeError):
                FacebookClient('page', 'token').post_photos(paths)
            self.assertTrue(all(call.args[0].endswith('/photos') for call in post.call_args_list))

    def test_generated_images_never_overwrite_each_other(self):
        from app.core.image_client import ImageClient
        with patch('app.core.image_client.OpenAI') as api, patch('app.core.image_client.time.time', return_value=12345):
            api.return_value.images.generate.return_value = Mock(
                usage=None, data=[Mock(b64_json='aW1hZ2U=', url=None)])
            client = ImageClient('fake')
            first = client.generate_image('Prompt', '1024x1024', self.video.parent)
            second = client.generate_image('Prompt', '1024x1024', self.video.parent)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), b'image')
            self.assertEqual(second.read_bytes(), b'image')

    def test_missing_image_blocks_entire_post(self):
        settings = {**self.settings, 'automation_platforms': ['facebook'], 'automation_attachment': 'image', 'automation_image_count': 2}
        with self.assertRaises(ValueError):
            publisher.publish_generated(settings, 'Caption', 'Topic', self.pages, image_paths=[self.video])
        self.facebook.assert_not_called()

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
        with patch("app.storage.history_store.save_post") as history:
            results = publisher.publish_and_archive(tab._run_settings, "caption", tab._run_topic,
                                                    tab._run_pages, video_path=self.video)
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

    def test_facebook_preview_follows_edits_selection_and_schedule(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap

        tab = AutomationTab()
        preview = tab.facebook_preview
        tab.review_text.setPlainText("<b>Offer</b>\n#demo")
        self.assertEqual(preview.content.text(), "<b>Offer</b>\n#demo")
        self.assertEqual(preview.content.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(preview.page_name.text(), "Demo Page")
        tab.schedule_check.setChecked(True)
        self.assertIn(tab.schedule_datetime.dateTime().toString("dd/MM/yyyy HH:mm"), preview.meta.text())
        tab.pages_selector.set_selected_ids([])
        self.assertEqual(preview.page_name.text(), "Page Facebook")
        image = QPixmap(80, 40)
        image.fill(Qt.GlobalColor.red)
        preview.set_media(image, "Rendering")
        preview.finish_video("demo.mp4")
        self.assertFalse(preview.media._original.isNull())
        self.assertIn("demo.mp4", preview.video_caption.text())
        preview.set_media()
        self.assertTrue(preview.media.isHidden())
        self.assertTrue(preview.video_caption.isHidden())

    def test_phone_frame_fits_preview_when_resized(self):
        tab = AutomationTab()
        for width, height in ((980, 680), (1240, 840), (1600, 1000)):
            tab.resize(width, height)
            tab.show()
            for _ in range(8):
                self.app.processEvents()
            view = tab.facebook_preview.phone_view
            bounds = view.mapFromScene(view.scene().sceneRect()).boundingRect()
            viewport = view.viewport().rect().adjusted(-1, -1, 1, 1)
            self.assertTrue(viewport.contains(bounds), (viewport, bounds))
            self.assertEqual(view.width(), tab.facebook_preview.width())
            self.assertGreaterEqual(bounds.height(), view.viewport().height() - 6)
            self.assertGreaterEqual(bounds.width(), view.viewport().width() - 6)
            self.assertEqual(view.verticalScrollBar().maximum(), 0)
            self.assertEqual(tab.facebook_preview.screen.width(), 390)
            self.assertEqual(tab.facebook_preview.screen.height(), 844)
            self.assertEqual(tab.phone_panel.geometry().right(), tab.width() - 1)
            self.assertEqual(tab.phone_panel.geometry().bottom(), tab.height() - 1)
            self.assertEqual(tab.controls_scroll.geometry().bottom(), tab.height() - 1)
        self.assertGreater(tab.facebook_preview.height(), 540)
        tab.close()

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
