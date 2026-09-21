"""Offline integration checks for durable published posts and editing."""
import os
import sys
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QColor
from app import config
from app.storage import history_store, sqlite_history_store as db
from app.storage.post_assets import attachment_paths
from app.core import automation_publisher as publisher, archived_posts
from app.core.youtube_client import YouTubeClient
from app.core.facebook_client import FacebookClient, post_to_pages
from app.ui.published_post_dialog import PublishedPostDialog


def settle(app, dialog):
    deadline = time.monotonic() + 5
    while dialog._busy:
        app.processEvents()
        assert time.monotonic() < deadline
        time.sleep(0.01)
    app.processEvents()


def main():
    app = QApplication([])
    from run import apply_theme
    apply_theme(app)
    with TemporaryDirectory() as directory, \
         patch.object(config, "app_data_dir", return_value=Path(directory)), \
         patch.object(db, "app_data_dir", return_value=Path(directory)), \
         patch.object(history_store, "_backend", return_value=db), \
         patch("requests.sessions.Session.request", side_effect=AssertionError("Unexpected network")):
        db.init_db()
        images = []
        for i, color in enumerate(("red", "blue")):
            path = Path(directory) / f"image{i}.png"
            pixmap = QPixmap(240, 180)
            pixmap.fill(QColor(color))
            assert pixmap.save(str(path))
            images.append(path)
        history_store.save_post("photos", "Nội dung đã đăng", json.dumps(list(map(str, images))),
                                facebook_post_id="123_456", page_id="123", page_name="Trang mẫu")
        row = db.list_successful_posts()[0]
        saved = attachment_paths(row)
        assert len(saved) == 2 and all(p.is_file() for p in saved)
        assert saved != images
        for path in images:
            path.unlink()
        assert all(p.is_file() for p in saved)
        assert (saved[0].parent / "post.json").is_file()
        history_store.save_post_draft(row, "Bản sửa")
        row = db.list_successful_posts()[0]
        assert row["message"] == "Nội dung đã đăng" and row["draft_message"] == "Bản sửa"
        dialog = PublishedPostDialog(row)
        dialog.show()
        app.processEvents()
        assert dialog.editor.toPlainText() == "Bản sửa"
        assert dialog.files.count() == 2
        dialog.files.setCurrentIndex(1)
        assert not dialog.phone.media._original.isNull()
        dialog.editor.setPlainText("Chỉnh sửa lần hai")
        dialog._save()
        settle(app, dialog)
        assert db.list_successful_posts()[0]["draft_message"] == "Chỉnh sửa lần hai"
        output = Path("output/ui-review/published-post-dialog.png")
        output.parent.mkdir(parents=True, exist_ok=True)
        dialog.grab().save(str(output))
        dialog.close()
        with patch.object(config, "get_page_token", return_value="fake"), \
             patch.object(FacebookClient, "update_post", side_effect=RuntimeError("API failure")):
            try:
                archived_posts.update_original(row, "Must not save")
                assert False
            except RuntimeError:
                pass
        assert db.list_successful_posts()[0]["message"] == "Nội dung đã đăng"
        with patch.object(config, "get_page_token", return_value="fake"), \
             patch.object(FacebookClient, "update_post", return_value={"success": True}):
            archived_posts.update_original(row, "Đã cập nhật")
        assert db.list_successful_posts()[0]["message"] == "Đã cập nhật"
        assert db.list_successful_posts()[0]["draft_message"] is None
        with patch.object(config, "get_page_token", return_value="fake"), \
             patch.object(archived_posts, "publish_and_archive", return_value=[{"ok": True}]) as publish:
            archived_posts.repost(dict(row, post_type="text", attachment_path="", link_url="https://example.com/article"), "", {})
            assert publish.call_args.args[0]["automation_facebook_link"] == "https://example.com/article"
        results = [dict(ok=True, name="Page", platform="facebook", post_type="text", post_id="123_789", id="123")]
        with patch.object(publisher, "publish_generated", return_value=results), \
             patch.object(history_store, "save_post", side_effect=OSError("Disk full")):
            result = publisher.publish_and_archive({}, "text", "topic", [])
            assert result[0]["ok"] and result[0]["archive_error"] == "Disk full"
        with patch.object(config, "get_page_token", return_value="fake"), \
             patch.object(publisher, "post_to_pages", return_value=[dict(ok=True, name="Page", id="123", post_id="123_900")]) as post:
            archived_posts.repost(row, "Đăng lại", {})
            assert post.call_args.kwargs["image_paths"] == saved
            assert post.call_args.kwargs["scheduled_time"] is None
            assert len(db.list_successful_posts()) == 2
        with patch.object(FacebookClient, "post_photo", return_value={"id": "photo", "post_id": "123_456"}):
            assert post_to_pages([dict(id="123", name="Page", token="fake")], "photo")[0]["post_id"] == "123_456"
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"items": [{"snippet": {"title": "Keep title", "categoryId": "22", "tags": ["keep"]}}]}
        updated = Mock(ok=True, status_code=200)
        updated.json.return_value = {"id": "video"}
        with patch("app.core.youtube_client.requests.get", return_value=response), \
             patch("app.core.youtube_client.requests.put", return_value=updated) as put:
            YouTubeClient("fake").update_description("video", "New description")
            payload = put.call_args.kwargs["json"]
            assert payload["snippet"] == dict(title="Keep title", categoryId="22", tags=["keep"], description="New description")
            assert "status" not in payload
        tik = PublishedPostDialog(dict(row, post_type="tiktok_video", attachment_path=""))
        assert not tik.update_btn.isEnabled()
        tik.close()
        video_path = Path(directory) / "video.mp4"
        video_path.write_bytes(b"offline-video")
        with patch("app.ui.published_post_dialog.QMediaPlayer") as player_class:
            video_dialog = PublishedPostDialog(dict(row, post_type="youtube_video", attachment_path=str(video_path)))
            player_class.return_value.setVideoSink.assert_called_once()
            frame = Mock()
            frame.toImage.return_value = pixmap.toImage()
            video_dialog._video_frame(frame)
            assert not video_dialog.phone.media._original.isNull()
            video_dialog._toggle_video()
            player_class.return_value.play.assert_called_once()
            video_dialog.close()
            player_class.return_value.stop.assert_called_once()
    print("PASS: durable media, drafts, mobile dialog, multi-photo repost, update failure/success, archive failure, API metadata preservation")


if __name__ == "__main__":
    main()
