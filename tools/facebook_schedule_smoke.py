"""Offline Facebook schedule storage, status and UI regression checks."""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from app import config
from app.storage import history_store, sqlite_history_store as db, mongo_store
from app.core.facebook_client import FacebookClient
from app.core.facebook_schedule import status_data, status_label, sync_posts, post_and_record
from app.ui.facebook_schedule_tab import FacebookScheduleTab, PAGE_SIZE
from run import apply_theme


def settle(app, tab):
    deadline = time.monotonic() + 8
    while tab._busy or tab._search_timer.isActive():
        app.processEvents()
        assert time.monotonic() < deadline, "Worker did not finish"
        time.sleep(0.01)
    app.processEvents()


def main():
    app = QApplication([])
    apply_theme(app)
    now = datetime.now().astimezone()
    future = (now + timedelta(days=1)).isoformat(timespec="minutes")
    past = (now - timedelta(days=1)).isoformat(timespec="minutes")
    with TemporaryDirectory() as folder, \
         patch.object(config, "app_data_dir", return_value=Path(folder)), \
         patch.object(db, "app_data_dir", return_value=Path(folder)), \
         patch.object(history_store, "_backend", return_value=db), \
         patch.object(config, "get_page_token", return_value="fake"), \
         patch("requests.sessions.Session.request", side_effect=AssertionError("Live network forbidden")):
        db.init_db()
        db.init_db()  # Migration is repeatable on existing databases.
        db.add_post("text", "Nội dung chờ đăng\nDòng thứ hai", scheduled_time=future,
                    facebook_post_id="123_1", page_id="123", page_name="Trang mẫu")
        db.add_post("text", "Quá giờ", scheduled_time=past, facebook_post_id="123_2", page_id="123")
        db.add_post("text", "Không nhận lịch", scheduled_time=future, ok=False, error="Token hết hạn")
        db.add_post("text", "Bài đăng ngay")
        db.add_post("youtube_video", "Không phải Facebook", scheduled_time=future)
        rows = db.list_scheduled_posts()
        assert len(rows) == 3
        assert len(db.list_scheduled_posts("TRANG MẪU")) == 1
        pending = next(row for row in rows if row["facebook_post_id"] == "123_1")
        overdue = next(row for row in rows if row["facebook_post_id"] == "123_2")
        failed = next(row for row in rows if not row["ok"])
        assert "chưa xác minh" in status_label(pending)
        assert status_label(overdue) == "Đã đến giờ — cần kiểm tra"
        assert status_label(failed) == "Lên lịch thất bại"
        assert status_data(failed)["error"] == "Token hết hạn"
        with patch.object(FacebookClient, "get_publication_status", return_value={"published": True, "message": "Đã sửa trên Facebook"}):
            published = sync_posts([overdue])[0]
        assert status_label(published) == "Đã đăng"
        assert status_data(db.list_scheduled_posts("Quá giờ")[0])["published"] is True
        with patch.object(FacebookClient, "get_publication_status", side_effect=RuntimeError("Thiếu quyền")):
            checked = sync_posts([published])[0]
        assert status_label(checked) == "Đã đăng"
        assert status_data(checked)["sync_error"] == "Thiếu quyền"
        with patch.object(FacebookClient, "get_publication_status", return_value={"published": False, "scheduled_time": future}):
            waiting = sync_posts([pending])[0]
        assert status_label(waiting) == "Chờ đăng"
        with patch.object(FacebookClient, "get_publication_status", return_value={"published": False}):
            assert status_label(sync_posts([overdue])[0]) == "Đã đến giờ — chưa đăng"
        with patch.object(config, "get_page_token", return_value=""):
            assert "Thiếu token" in status_data(sync_posts([waiting])[0])["sync_error"]
        with patch.object(FacebookClient, "get_publication_status", return_value={}) as api:
            assert "chưa trả về" in status_data(sync_posts([pending])[0])["sync_error"]
            sync_posts([failed])
            assert api.call_count == 1
        with patch("app.core.facebook_schedule.post_to_pages", return_value=[
                dict(id="123", name="Trang mẫu", ok=True, post_id="123_3"),
                dict(id="456", name="Trang lỗi", ok=False, error="Permission denied")]):
            post_and_record([], "text", "Lịch mới", message="Lịch mới", scheduled_time=int(now.timestamp()) + 3600)
        saved = db.list_scheduled_posts("Lịch mới")
        assert len(saved) == 2 and any(status_data(row).get("error") == "Permission denied" for row in saved)
        with patch("app.core.facebook_schedule.post_to_pages", return_value=[dict(
                id="123", name="Trang mẫu", ok=False, uncertain=True, error="Timeout")]):
            post_and_record([], "text", "Chưa xác nhận", message="Chưa xác nhận",
                            scheduled_time=int(now.timestamp()) + 3600)
        unknown = db.list_scheduled_posts("Chưa xác nhận")[0]
        assert status_label(unknown) == "Chưa xác nhận — kiểm tra Page"
        db.delete_item("posts", unknown["id"])
        with patch("app.core.facebook_schedule.post_to_pages", return_value=[dict(
                id="123", name="Trang mẫu", ok=True, post_id="123_88")]):
            post_and_record([], "text", "", message="", link="https://example.com/article")
        assert db.list_successful_posts()[0]["link_url"] == "https://example.com/article"
        response = Mock(ok=True)
        response.json.return_value = {"id": "42", "published": False}
        with patch("app.core.facebook_client.requests.get", return_value=response) as get:
            client = FacebookClient("123", "fake")
            assert client.get_publication_status("42", "video")["published"] is False
            assert "published," in get.call_args.kwargs["params"]["fields"]
            response.json.return_value = {"is_published": True}
            assert client.get_publication_status("123_4", "text")["published"] is True
            assert "is_published" in get.call_args.kwargs["params"]["fields"]
        tab = FacebookScheduleTab()
        tab.resize(1050, 760)
        tab.show()
        tab.refresh()
        settle(app, tab)
        assert tab.table.rowCount() == 5
        tab.search.setText("Nội dung chờ")
        settle(app, tab)
        assert tab.table.rowCount() == 1
        assert "Dòng thứ hai" in tab.content.toPlainText()
        with patch.object(FacebookClient, "get_publication_status", return_value={"published": True}):
            tab.check_btn.click()
            settle(app, tab)
        assert tab.table.item(0, 3).text() == "Đã đăng"
        tab.search.clear()
        settle(app, tab)
        output = Path("output/ui-review/facebook-schedule.png")
        output.parent.mkdir(parents=True, exist_ok=True)
        tab.grab().save(str(output))
        for i in range(PAGE_SIZE):
            db.add_post("text", f"Lịch {i}", scheduled_time=future)
        tab.refresh()
        settle(app, tab)
        assert tab.table.rowCount() == PAGE_SIZE and tab.next_btn.isEnabled()
        tab.next_btn.click()
        settle(app, tab)
        assert tab.table.rowCount() == 5 and tab.previous_btn.isEnabled()
        tab.search.setText("Không tồn tại")
        settle(app, tab)
        assert tab.table.rowCount() == 0 and not tab.check_btn.isEnabled()
        tab.close()
        collection = Mock()
        collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = []
        with patch.object(mongo_store, "_get_db", return_value={"posts": collection}):
            mongo_store.list_scheduled_posts("100%")
            criteria = collection.find.call_args.args[0]
            assert "ok" not in criteria and "youtube_video" not in criteria["post_type"]["$in"]
            mongo_store.update_post_fields("row", {"schedule_status": "{}"})
            collection.update_one.assert_called_once()
    print("PASS: schedule persistence, failure reasons, remote evidence, overdue states, API fields, SQLite/Mongo, search, paging, UI sync")


if __name__ == "__main__":
    main()
