"""Publish one generated asset to configured destinations, isolating each failure."""
from pathlib import Path

from app import config
from app.core.facebook_client import post_to_pages
from app.core.social_tokens import ensure_tiktok_token, ensure_youtube_token
from app.core.tiktok_client import TikTokClient
from app.core.youtube_client import YouTubeClient

PLATFORM_LABELS = {"facebook": "Facebook", "tiktok": "TikTok", "youtube": "YouTube"}


def selected_platforms(settings):
    values = settings.get("automation_platforms", ["facebook"])
    if not isinstance(values, list):
        return []
    return [key for key in PLATFORM_LABELS if key in values]


def configured_pages(settings):
    ids = settings.get("automation_facebook_page_ids", [])
    return [{**page, "token": config.get_page_token(page["id"])}
            for page in config.list_pages() if page.get("id") in ids]


def validate_destinations(settings, pages):
    platforms = selected_platforms(settings)
    if not platforms:
        raise ValueError("Chọn ít nhất một nền tảng trong Cài đặt quy trình.")
    if any(key in platforms for key in ("tiktok", "youtube")) and settings.get("automation_attachment") != "video":
        raise ValueError("TikTok và YouTube cần loại đính kèm Video trong Cài đặt quy trình.")
    if "facebook" in platforms:
        if not pages:
            raise ValueError("Chọn Page Facebook trong Cài đặt quy trình.")
        if any(not page.get("token") for page in pages):
            raise ValueError("Page Facebook thiếu token. Kết nối lại Page trước khi chạy.")
    for platform, getter in (("tiktok", config.get_tiktok_account), ("youtube", config.get_youtube_account)):
        if platform in platforms and not getter().get("access_token"):
            raise ValueError(f"Kết nối {PLATFORM_LABELS[platform]} trước khi chạy quy trình.")


def publish_generated(settings, message, topic, pages, image_path=None, video_path=None,
                      scheduled_time=None, skip_targets=None, on_progress=None):
    results = []
    skipped = set(skip_targets or ())
    attachment = settings.get("automation_attachment", "image")
    path = image_path if attachment == "image" else video_path if attachment == "video" else None
    if attachment != "none" and (not path or not Path(path).is_file()):
        raise ValueError("Không tìm thấy ảnh/video đã tạo. Chạy lại quy trình.")
    platforms = selected_platforms(settings)
    for platform in platforms:
        if platform == "facebook":
            pending = [page for page in pages if f"facebook:{page['id']}" not in skipped]
            if not pending:
                continue
            post_type = {"none": "text", "image": "photo", "video": "video"}[attachment]
            kwargs = {"scheduled_time": scheduled_time}
            if post_type == "photo":
                kwargs.update(image_path=image_path, caption=message)
            elif post_type == "video":
                kwargs.update(video_path=video_path, description=message)
            else:
                kwargs.update(message=message, link=None)
            for result in post_to_pages(pending, post_type, on_progress=on_progress, **kwargs):
                results.append({**result, "platform": platform, "target": f"facebook:{result['id']}",
                                "post_type": post_type, "attachment_path": str(path or "")})
            continue
        if platform in skipped:
            continue
        result = {"platform": platform, "target": platform, "name": PLATFORM_LABELS[platform],
                  "id": "", "post_type": f"{platform}_video", "attachment_path": str(video_path or "")}
        try:
            if not video_path or not Path(video_path).is_file():
                raise ValueError(f"{result['name']} cần video đã tạo.")
            if on_progress:
                on_progress(f"Đang đăng video lên {result['name']}...")
            if platform == "tiktok":
                client = TikTokClient(ensure_tiktok_token(on_progress))
                creator = client.query_creator_info()
                privacy = settings.get("automation_tiktok_privacy", "SELF_ONLY")
                if privacy not in creator.get("privacy_level_options", []):
                    raise ValueError("Quyền riêng tư TikTok đã chọn không khả dụng cho tài khoản này.")
                data = client.post_video(Path(video_path), title=message[:2200], privacy_level=privacy,
                    disable_comment=bool(settings.get("automation_tiktok_disable_comment")) or bool(creator.get("comment_disabled")),
                    disable_duet=bool(settings.get("automation_tiktok_disable_duet")) or bool(creator.get("duet_disabled")),
                    disable_stitch=bool(settings.get("automation_tiktok_disable_stitch")) or bool(creator.get("stitch_disabled")),
                    on_progress=on_progress)
                ids = data.get("publicaly_available_post_id", [])
                post_id = str(ids[0]) if ids else data.get("publish_id", "")
            else:
                title = settings.get("automation_youtube_title", "").strip() or topic.strip() or "Video mới"
                data = YouTubeClient(ensure_youtube_token(on_progress)).upload_video(Path(video_path),
                    title=title.replace("<", "").replace(">", "")[:100],
                    description=message.replace("<", "").replace(">", "")[:5000],
                    tags=[tag.strip() for tag in settings.get("automation_youtube_tags", "").split(",") if tag.strip()],
                    category_id=settings.get("automation_youtube_category", "22"),
                    privacy_status=settings.get("automation_youtube_privacy", "private"), on_progress=on_progress)
                post_id = data.get("id", "")
            result.update(ok=True, post_id=post_id)
        except Exception as exc:
            result.update(ok=False, error=str(exc))
        results.append(result)
    return results
