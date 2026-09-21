"""Explicit publishing actions for an archived post."""
from app import config
from app.core.automation_publisher import publish_and_archive
from app.core.facebook_client import FacebookClient
from app.core.social_tokens import ensure_youtube_token
from app.core.youtube_client import YouTubeClient
from app.storage import history_store
from app.storage.post_assets import attachment_paths


def platform_for(row):
    kind = row.get("post_type", "")
    return "youtube" if kind.startswith("youtube") else "tiktok" if kind.startswith("tiktok") else "facebook"


def repost(row, message, settings, on_progress=None):
    platform = platform_for(row)
    paths = attachment_paths(row)
    if any(not path.is_file() for path in paths):
        raise ValueError("Thiếu tệp đính kèm trong kho. Khôi phục tệp trước khi đăng lại.")
    kind = row["post_type"]
    attachment = "none" if kind == "text" else "image" if kind in ("photo", "photos") else "video"
    settings = dict(settings, automation_platforms=[platform], automation_attachment=attachment,
                    automation_image_count=len(paths), automation_facebook_link=row.get("link_url") or "")
    pages = []
    if platform == "facebook":
        page_id = row.get("page_id")
        token = config.get_page_token(page_id) if page_id else ""
        if not token:
            raise ValueError("Kết nối lại Page gốc trước khi đăng lại.")
        pages = [dict(id=page_id, name=row.get("page_name") or page_id, token=token)]
    results = publish_and_archive(settings, message, message.splitlines()[0][:100] if message else "Video mới",
                                  pages, image_paths=paths if attachment == "image" else None,
                                  video_path=paths[0] if paths and attachment == "video" else None,
                                  on_progress=on_progress)
    if not results or not results[0]["ok"]:
        raise RuntimeError(results[0].get("error", "Đăng thất bại") if results else "Không có nơi đăng.")
    result = results[0]
    return "Đã đăng lại thành bài mới." + (f" Chưa lưu đủ vào kho: {result['archive_error']}"
                                            if result.get("archive_error") else " Đã lưu vào kho.")


def update_original(row, message):
    platform = platform_for(row)
    identity = row.get("facebook_post_id")
    if not identity:
        raise ValueError("Bài viết thiếu mã bài gốc.")
    if platform == "tiktok":
        raise ValueError("Chưa hỗ trợ cập nhật bài TikTok. Hãy dùng Đăng lại.")
    if platform == "youtube":
        YouTubeClient(ensure_youtube_token()).update_description(identity, message)
    else:
        page_id = row.get("page_id")
        FacebookClient(page_id, config.get_page_token(page_id) if page_id else "").update_post(
            identity, message, row["post_type"])
    try:
        history_store.mark_post_updated(row, message)
    except Exception as exc:
        return f"Đã cập nhật trên nền tảng nhưng chưa đồng bộ kho: {exc}"
    return "Đã cập nhật nội dung bài gốc và đồng bộ kho."
