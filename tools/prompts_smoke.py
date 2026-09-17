"""Offline checks for prompt persistence, editing and provider integration."""
import os
import sys
import tempfile
import unittest
import gc
import threading
import weakref
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import config
from app.core.content_prompts import POST_PROMPT_KEY, SYSTEM_PROMPT_POST, get_post_system_prompt, save_post_system_prompt
from app.core.claude_client import ClaudeClient
from app.core.openai_content_client import OpenAIContentClient
from app.storage import history_store, mongo_store, sqlite_history_store
from app.ui.content_tab import ContentTab
from app.ui.automation_tab import AutomationTab
from app.ui.widgets.post_prompt_editor import PostPromptEditor
from app.workers.async_worker import Worker


class PromptChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "history.sqlite3"
        self.stack.enter_context(patch.object(sqlite_history_store, "_db_path", return_value=self.path))
        self.stack.enter_context(patch.object(config, "get_secret", return_value=""))
        self.stack.enter_context(patch.object(config, "load_settings", side_effect=lambda: dict(config.DEFAULT_SETTINGS)))
        self.stack.enter_context(patch.object(config, "save_settings"))
        self.stack.enter_context(patch.object(config, "list_pages", return_value=[]))
        self.stack.enter_context(patch.object(history_store, "add_content"))
        self.stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("Live API call")))
        sqlite_history_store.init_db()

    def wait(self, condition):
        for _ in range(150):
            QTest.qWait(20)
            if condition():
                return
        self.fail("Background prompt operation did not finish")

    def widget(self, cls):
        widget = cls()
        self.addCleanup(widget.deleteLater)
        return widget

    def test_default_and_unicode_upsert_survive_reopen(self):
        self.assertEqual(get_post_system_prompt(), SYSTEM_PROMPT_POST)
        self.assertIsNone(history_store.get_prompt(POST_PROMPT_KEY))
        first = "Bạn là chuyên gia viết nội dung tiếng Việt.\nKhông dùng emoji."
        self.assertEqual(save_post_system_prompt("  " + first + "  "), first)
        self.assertEqual(get_post_system_prompt(), first)
        replacement = "Viết nội dung ngắn, rõ ràng, hướng đến người đọc."
        save_post_system_prompt(replacement)
        sqlite_history_store.init_db()
        self.assertEqual(get_post_system_prompt(), replacement)
        with sqlite_history_store._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM prompts").fetchone()[0], 1)
            self.assertTrue(connection.execute("SELECT updated_at FROM prompts").fetchone()[0])

    def test_schema_upgrade_keeps_existing_history(self):
        sqlite_history_store.add_content("Existing", "Keep this content")
        with sqlite_history_store._connect() as connection:
            connection.execute("DROP TABLE prompts")
        self.assertEqual(get_post_system_prompt(), SYSTEM_PROMPT_POST)
        save_post_system_prompt("Custom prompt")
        with sqlite_history_store._connect() as connection:
            self.assertEqual(connection.execute("SELECT text FROM contents").fetchone()[0], "Keep this content")

    def test_empty_prompt_rejected_without_overwriting(self):
        save_post_system_prompt("Keep the saved prompt")
        with self.assertRaises(ValueError):
            save_post_system_prompt(" \n ")
        self.assertEqual(get_post_system_prompt(), "Keep the saved prompt")

    def test_mongodb_routing_and_acknowledged_errors(self):
        collection = Mock()
        collection.find_one.return_value = {"text": "Mongo prompt"}
        with patch.object(config, "get_secret", return_value="mongodb://offline"), \
             patch.object(mongo_store, "_get_db", return_value={"prompts": collection}):
            self.assertEqual(get_post_system_prompt(), "Mongo prompt")
            save_post_system_prompt("Changed Mongo prompt")
            collection.update_one.assert_called_once()
            args, kwargs = collection.update_one.call_args
            self.assertEqual(args[0], {"_id": POST_PROMPT_KEY})
            self.assertEqual(args[1]["$set"]["text"], "Changed Mongo prompt")
            self.assertTrue(kwargs["upsert"])
            collection.update_one.side_effect = RuntimeError("DB unavailable")
            with self.assertRaisesRegex(RuntimeError, "DB unavailable"):
                save_post_system_prompt("Never claim saved")
            collection.find_one.side_effect = RuntimeError("DB unavailable")
            with self.assertRaises(RuntimeError):
                get_post_system_prompt()

    def test_both_providers_use_saved_prompt_and_current_form_values(self):
        save_post_system_prompt("Shared custom system prompt")
        for cls in (ClaudeClient, OpenAIContentClient):
            client = cls.__new__(cls)
            client._complete = Mock(return_value="Generated content")
            client.generate_post("Demo topic", tone="Demo tone", audience="Demo readers", include_hashtags=False)
            args = client._complete.call_args.args
            self.assertEqual(args[0], "Shared custom system prompt")
            self.assertIn("Demo topic", args[1])
            self.assertIn("Demo tone", args[1])
            self.assertIn("Demo readers", args[1])
            client.generate_post("topic", system_prompt="Explicit snapshot")
            self.assertEqual(client._complete.call_args.args[0], "Explicit snapshot")

    def test_batch_uses_one_prompt_snapshot(self):
        save_post_system_prompt("First prompt")
        client = Mock()
        def generate(**kwargs):
            save_post_system_prompt("Later prompt")
            return kwargs["system_prompt"]
        client.generate_post.side_effect = generate
        self.assertEqual(ContentTab._generate_batch(client, count=3, topic="topic"), ["First prompt"] * 3)

    def test_editor_load_save_reopen_and_restore_default(self):
        editor = self.widget(PostPromptEditor)
        editor.toggle_btn.setChecked(True)
        self.wait(lambda: not editor.busy)
        self.assertEqual(editor.editor.toPlainText(), SYSTEM_PROMPT_POST)
        editor.editor.setPlainText("Prompt chỉnh sửa tiếng Việt")
        self.assertTrue(editor.dirty)
        self.assertEqual(get_post_system_prompt(), SYSTEM_PROMPT_POST)
        editor.save_btn.click()
        self.wait(lambda: not editor.busy)
        self.assertFalse(editor.dirty)
        self.assertEqual(get_post_system_prompt(), "Prompt chỉnh sửa tiếng Việt")
        reopened = self.widget(PostPromptEditor)
        reopened.toggle_btn.setChecked(True)
        self.wait(lambda: not reopened.busy)
        self.assertEqual(reopened.editor.toPlainText(), "Prompt chỉnh sửa tiếng Việt")
        reopened.reset_btn.click()
        self.assertTrue(reopened.dirty)
        self.assertEqual(get_post_system_prompt(), "Prompt chỉnh sửa tiếng Việt")
        reopened.save_btn.click()
        self.wait(lambda: not reopened.busy)
        self.assertEqual(get_post_system_prompt(), SYSTEM_PROMPT_POST)

    def test_save_failure_preserves_dirty_editor_and_reports_error(self):
        editor = self.widget(PostPromptEditor)
        editor.toggle_btn.setChecked(True)
        self.wait(lambda: not editor.busy)
        editor.editor.setPlainText("Unsaved edited prompt")
        with patch.object(history_store, "save_prompt", side_effect=RuntimeError("Save failed")), \
             patch("app.workers.async_worker.traceback.print_exc"):
            editor.save()
            self.wait(lambda: not editor.busy)
        self.assertTrue(editor.dirty)
        self.assertIn("Save failed", editor.status_label.text())
        self.assertEqual(get_post_system_prompt(), SYSTEM_PROMPT_POST)

    def test_unsaved_edits_block_generation(self):
        tab = self.widget(ContentTab)
        tab.topic_input.setText("Demo topic")
        tab.prompt_editor.toggle_btn.setChecked(True)
        self.wait(lambda: not tab.prompt_editor.busy)
        tab.prompt_editor.editor.setPlainText("Not saved")
        with patch("app.ui.content_tab.get_text_client") as factory:
            tab._on_generate()
            factory.assert_not_called()

    def test_automation_uses_saved_content_prompt(self):
        save_post_system_prompt("Custom automation prompt")
        tab = self.widget(AutomationTab)
        self.addCleanup(tab.processing_dialog.close)
        tab.idea_input.setPlainText("Automation topic")
        client = ClaudeClient.__new__(ClaudeClient)
        client._complete = Mock(return_value="Automatic content")
        settings = {**config.DEFAULT_SETTINGS, "automation_attachment": "none", "automation_auto_post": False}
        with patch.object(config, "load_settings", return_value=settings), \
             patch("app.ui.automation_tab.get_text_client", return_value=client):
            tab._on_run_pipeline()
            self.wait(lambda: tab.run_btn.isEnabled())
            tab._worker.wait(1000)
        self.assertEqual(client._complete.call_args.args[0], "Custom automation prompt")
        self.assertEqual(tab.review_text.toPlainText(), "Automatic content")

    def test_worker_survives_result_until_native_thread_stops(self):
        release = threading.Event()
        self.addCleanup(release.set)
        class FinishingWorker(Worker):
            def run(self):
                super().run()
                release.wait(2)
        results = []
        worker = FinishingWorker(lambda: "finished result")
        worker.finished.connect(results.append)
        reference = weakref.ref(worker)
        worker.start()
        del worker
        gc.collect()
        self.wait(lambda: bool(results))
        self.assertIsNotNone(reference())
        self.assertTrue(reference().isRunning())
        release.set()
        self.wait(lambda: reference() is None or not reference().isRunning())
        self.wait(lambda: reference() is None or reference() not in Worker._active_workers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
