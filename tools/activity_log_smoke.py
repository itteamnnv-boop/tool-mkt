"""Offline regression checks for durable activity logs. Uses only a temporary DB."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from app import config
from app.storage import history_store, mongo_store, sqlite_history_store
from app.ui.log_tab import LogTab
from app.ui.widgets.log_console import LogConsole


class ActivityLogChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "history.sqlite3"
        patcher = patch.object(sqlite_history_store, "_db_path", return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        secret_patcher = patch.object(config, "get_secret", return_value="")
        secret_patcher.start()
        self.addCleanup(secret_patcher.stop)

    def console(self):
        widget = LogConsole()
        self.addCleanup(widget.deleteLater)
        return widget

    def test_restart_in_separate_process_preserves_log_and_timestamp(self):
        script = '''
import sys
from pathlib import Path
from app.storage import sqlite_history_store
from app import config
config.get_secret = lambda key: ""
from app.ui.widgets.log_console import LogConsole
from PySide6.QtWidgets import QApplication
sqlite_history_store._db_path = lambda: Path(sys.argv[1])
app = QApplication([])
console = LogConsole()
console.log("Đã tạo ảnh\\nChi tiết tiếng Việt", "success")
console.log("Lỗi kết nối", "error")
'''
        subprocess.run([sys.executable, "-c", script, str(self.path)], cwd=ROOT, check=True)
        before = history_store.list_activity_logs()
        console = self.console()
        self.assertIn("✓ Đã tạo ảnh\nChi tiết tiếng Việt", console.toPlainText())
        self.assertIn("✗ Lỗi kết nối", console.toPlainText())
        self.assertEqual(history_store.list_activity_logs(), before)
        self.assertEqual(len(before), 2)
        self.assertIn(before[0]["created_at"][0:4], console.toPlainText())

    def test_clear_button_deletes_saved_logs_only(self):
        sqlite_history_store.init_db()
        sqlite_history_store.add_content("Topic", "Keep me")
        tab = LogTab()
        self.addCleanup(tab.deleteLater)
        tab.console.log("Old entry")
        tab.clear_btn.click()
        self.assertEqual(tab.console.toPlainText(), "")
        self.assertEqual(self.console().toPlainText(), "")
        self.assertEqual(sqlite_history_store.list_contents()[0]["text"], "Keep me")
        tab.console.log("New entry")
        self.assertIn("New entry", self.console().toPlainText())

    def test_recent_window_keeps_older_rows_in_database(self):
        sqlite_history_store.init_db()
        with sqlite_history_store._connect() as conn:
            conn.executemany(
                "INSERT INTO activity_logs (created_at, level, message) VALUES (?, ?, ?)",
                [("2026-09-22T12:00:00", "info", f"entry {i}") for i in range(2005)],
            )
        rows = history_store.list_activity_logs()
        self.assertEqual(len(rows), 2000)
        self.assertEqual(rows[0]["message"], "entry 5")
        self.assertEqual(rows[-1]["message"], "entry 2004")
        self.assertEqual(len(history_store.list_activity_logs(3000)), 2005)

    def test_storage_errors_are_visible_and_clear_failure_preserves_text(self):
        console = self.console()
        with patch.object(history_store, "add_activity_log", side_effect=OSError("disk full")), \
             patch("traceback.print_exc"):
            console.log("Keep visible")
        self.assertIn("Không thể lưu nhật ký", console.toPlainText())
        with patch.object(history_store, "clear_activity_logs", side_effect=OSError("locked")), \
             patch("traceback.print_exc"):
            console.clear()
        self.assertIn("Keep visible", console.toPlainText())
        self.assertIn("Không thể xoá nhật ký", console.toPlainText())
        with patch.object(history_store, "list_activity_logs", side_effect=OSError("locked")), \
             patch("traceback.print_exc"):
            self.assertIn("Không thể tải nhật ký", self.console().toPlainText())

    def test_mongo_save_reload_order_and_clear(self):
        collection = Mock()
        cursor = collection.find.return_value
        cursor.sort.return_value = cursor
        cursor.limit.return_value = []
        with patch.object(config, "get_secret", return_value="mongodb://offline"), \
             patch.object(mongo_store, "_get_db", return_value={"activity_logs": collection}):
            console = self.console()
            console.log("Đã lưu MongoDB", "success")
            saved = collection.insert_one.call_args.args[0]
            self.assertIsInstance(saved["created_at"], datetime)
            self.assertEqual(saved["message"], "Đã lưu MongoDB")
            self.assertEqual(saved["level"], "success")
            older = {"created_at": datetime(2026, 9, 22, 12), "message": "Earlier", "level": "info"}
            cursor.limit.side_effect = lambda limit: [dict(saved), dict(older)]
            restored = self.console().toPlainText()
            self.assertLess(restored.index("Earlier"), restored.index("Đã lưu MongoDB"))
            self.assertIn("22/09/2026 12:00:00", restored)
            self.assertIn("✓ Đã lưu MongoDB", restored)
            cursor.sort.assert_called_with("_id", -1)
            cursor.limit.assert_called_with(2000)
            console.clear()
            collection.delete_many.assert_called_once_with({})
            self.assertEqual(console.toPlainText(), "")
        self.assertFalse(self.path.exists(), "Mongo logs must not silently write to SQLite")

    def test_mongo_failure_does_not_fall_back_to_sqlite(self):
        collection = Mock()
        collection.insert_one.side_effect = RuntimeError("Mongo unavailable")
        with patch.object(config, "get_secret", return_value="mongodb://offline"), \
             patch.object(mongo_store, "_get_db", return_value={"activity_logs": collection}):
            with self.assertRaisesRegex(RuntimeError, "Mongo unavailable"):
                history_store.add_activity_log("Message", "info", "2026-09-23T12:00:00")
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
