"""Wraps the Facebook Graph API for posting text/photo/video to a Page."""
from __future__ import annotations

import re
import json
import urllib.parse
import time
from pathlib import Path

import requests

GRAPH_URL = "https://graph.facebook.com/v26.0"


class PublicationUnconfirmed(RuntimeError):
    """The request may have reached Facebook; do not automatically retry it."""


def validate_schedule(scheduled_time):
    if scheduled_time is not None:
        if isinstance(scheduled_time, bool) or not isinstance(scheduled_time, int):
            raise ValueError("Giờ hẹn Facebook không hợp lệ.")
        if scheduled_time < time.time() + 600:
            raise ValueError("Giờ hẹn phải còn ít nhất 10 phút tại lúc gửi. Hãy chọn giờ muộn hơn.")


class FacebookClient:
    def __init__(self, page_id: str, page_access_token: str):
        if not page_id or not page_access_token:
            raise ValueError("Thiếu Facebook Page ID hoặc Page Access Token. Vào Cài đặt để nhập.")
        self.page_id = page_id
        self.token = page_access_token

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        if resp.ok:
            return
        try:
            detail = resp.json().get("error", {}).get("message", resp.text)
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"Facebook Graph API lỗi ({resp.status_code}): {detail}")

    def post_text(self, message: str, link: str | None = None, scheduled_time: int | None = None) -> dict:
        validate_schedule(scheduled_time)
        if not message.strip() and not (link or "").strip():
            raise ValueError("Bài viết cần nội dung hoặc đường dẫn.")
        params = {"message": message, "access_token": self.token}
        if link:
            params["link"] = link
        if scheduled_time:
            params["published"] = "false"
            params["scheduled_publish_time"] = scheduled_time
        resp = requests.post(f"{GRAPH_URL}/{self.page_id}/feed", data=params, timeout=60)
        self._raise_for_status(resp)
        return resp.json()

    def update_post(self, post_id: str, message: str, post_type: str) -> dict:
        if not re.fullmatch(r"[0-9_]+", post_id):
            raise ValueError("Mã bài Facebook không hợp lệ.")
        field = "description" if post_type == "video" and "_" not in post_id else "message"
        resp = requests.post(f"{GRAPH_URL}/{post_id}",
                             data={"access_token": self.token, field: message}, timeout=60)
        self._raise_for_status(resp)
        data = resp.json()
        if data is False or (isinstance(data, dict) and data.get("success") is False):
            raise RuntimeError("Facebook chưa xác nhận cập nhật bài viết.")
        return data

    def get_publication_status(self, post_id: str, post_type: str) -> dict:
        if not re.fullmatch(r"[0-9_]+", post_id):
            raise ValueError("Mã bài Facebook không hợp lệ hoặc bị thiếu.")
        video = post_type == "video" and "_" not in post_id
        fields = ("id,published,scheduled_publish_time,description,status" if video else
                  "id,is_published,scheduled_publish_time,message")
        # Old photo records may contain only a media ID; resolve the Page post.
        identity = f"{self.page_id}_{post_id}" if post_type == "photo" and "_" not in post_id else post_id
        response = requests.get(f"{GRAPH_URL}/{identity}",
                                params={"access_token": self.token, "fields": fields}, timeout=30)
        self._raise_for_status(response)
        data = response.json()
        return {"published": data.get("published" if video else "is_published"),
                "scheduled_time": data.get("scheduled_publish_time"),
                "message": data.get("description" if video else "message"),
                "video_status": data.get("status", {})}

    def post_photo(self, image_path: Path, caption: str = "", scheduled_time: int | None = None) -> dict:
        validate_schedule(scheduled_time)
        params = {"caption": caption, "access_token": self.token}
        if scheduled_time:
            params["published"] = "false"
            params["scheduled_publish_time"] = scheduled_time
        with open(image_path, "rb") as f:
            files = {"source": (image_path.name, f, "application/octet-stream")}
            resp = requests.post(f"{GRAPH_URL}/{self.page_id}/photos", data=params, files=files, timeout=180)
        self._raise_for_status(resp)
        return resp.json()

    def post_photos(self, image_paths: list[Path], caption: str = "", scheduled_time: int | None = None) -> dict:
        validate_schedule(scheduled_time)
        if not image_paths or any(not Path(path).is_file() for path in image_paths):
            raise ValueError("Không tìm thấy đầy đủ ảnh để đăng bài.")
        media = []
        for path in image_paths:
            path = Path(path)
            with path.open("rb") as stream:
                response = requests.post(
                    f"{GRAPH_URL}/{self.page_id}/photos",
                    data={"access_token": self.token, "published": "false", "temporary": "true"},
                    files={"source": (path.name, stream, "application/octet-stream")}, timeout=180,
                )
            self._raise_for_status(response)
            photo_id = response.json().get("id")
            if not photo_id:
                raise RuntimeError("Facebook không trả về ID ảnh. Chưa đăng bài.")
            media.append({"media_fbid": photo_id})
        params = {"message": caption, "access_token": self.token, "attached_media": json.dumps(media)}
        validate_schedule(scheduled_time)  # Uploading the album may have consumed the scheduling window.
        if scheduled_time:
            params.update(published="false", scheduled_publish_time=scheduled_time)
        response = requests.post(f"{GRAPH_URL}/{self.page_id}/feed", data=params, timeout=60)
        self._raise_for_status(response)
        return response.json()

    def post_video(self, video_path: Path, description: str = "", scheduled_time: int | None = None) -> dict:
        validate_schedule(scheduled_time)
        params = {"description": description, "access_token": self.token}
        if scheduled_time:
            params["published"] = "false"
            params["scheduled_publish_time"] = scheduled_time
        with open(video_path, "rb") as f:
            files = {"source": (video_path.name, f, "video/mp4")}
            resp = requests.post(f"{GRAPH_URL}/{self.page_id}/videos", data=params, files=files, timeout=600)
        self._raise_for_status(resp)
        return resp.json()

    @staticmethod
    def list_pages_for_token(user_access_token: str) -> list[dict]:
        """Given a User Access Token, list every Page the user manages (id, name, category,
        access_token). Each returned access_token is that Page's own token — this is how
        'Connect Facebook' discovers all pages in one step instead of hunting for each token."""
        resp = requests.get(
            f"{GRAPH_URL}/me/accounts",
            params={"access_token": user_access_token, "fields": "id,name,category,access_token"},
            timeout=30,
        )
        FacebookClient._raise_for_status(resp)
        return resp.json().get("data", [])

    @staticmethod
    def exchange_for_long_lived_token(app_id: str, app_secret: str, short_lived_token: str) -> str:
        """Exchanges a short-lived User Access Token (~1-2h) for a long-lived one (~60 days).
        Page tokens derived from a long-lived user token do not expire on a fixed schedule,
        so doing this before 'Connect' keeps posting working for a long time."""
        if not app_id or not app_secret:
            raise ValueError("Cần nhập Facebook App ID và App Secret trong Cài đặt trước.")
        resp = requests.get(
            f"{GRAPH_URL}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_lived_token,
            },
            timeout=30,
        )
        FacebookClient._raise_for_status(resp)
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("Facebook không trả về access_token dài hạn.")
        return token

    @staticmethod
    def whoami(token: str) -> dict:
        """Calls GET /me with the given token. For a genuine Page Access Token this returns the
        Page's own id/name; for a User Access Token it returns the person's id/name instead —
        used to detect the wrong token type before it causes a confusing post failure."""
        resp = requests.get(
            f"{GRAPH_URL}/me",
            params={"fields": "id,name", "access_token": token},
            timeout=15,
        )
        FacebookClient._raise_for_status(resp)
        return resp.json()


def post_to_pages(pages: list[dict], post_type: str, on_progress=None, **kwargs) -> list[dict]:
    """Posts the same content to several Pages in one go.

    pages: list of {"id", "name", "token"}. post_type: "text" | "photo" | "video".
    kwargs are forwarded to the matching FacebookClient.post_* method.
    Returns one result dict per page so a failure on one page never blocks the others.
    """
    if post_type not in {"text", "photo", "photos", "video"}:
        raise ValueError("Loại bài Facebook không được hỗ trợ.")
    results = []
    total = len(pages)
    for idx, page in enumerate(pages, start=1):
        if on_progress:
            on_progress(f"Đang đăng lên '{page['name']}' ({idx}/{total})...")
        try:
            client = FacebookClient(page["id"], page["token"])
            if post_type == "photos":
                data = client.post_photos(**kwargs)
            elif post_type == "photo":
                data = client.post_photo(**kwargs)
            elif post_type == "video":
                data = client.post_video(**kwargs)
            else:
                data = client.post_text(**kwargs)
            identity = (data.get("post_id") or data.get("id")) if isinstance(data, dict) else None
            if not identity:
                raise PublicationUnconfirmed("Facebook chưa trả về mã bài. Kiểm tra Page trước khi đăng lại để tránh trùng bài.")
            results.append({"id": page["id"], "name": page["name"], "ok": True, "post_id": str(identity)})
        except Exception as exc:  # noqa: BLE001 - one page's failure must not abort the rest
            uncertain = isinstance(exc, (PublicationUnconfirmed, requests.Timeout, requests.ConnectionError))
            error = str(exc).replace(page["token"], "[token]") if page.get("token") else str(exc)
            if uncertain and not isinstance(exc, PublicationUnconfirmed):
                error = "Mất kết nối, chưa xác nhận kết quả. Kiểm tra Page trước khi đăng lại. " + error
            results.append({"id": page["id"], "name": page["name"], "ok": False,
                            "uncertain": uncertain, "error": error})
    return results


def extract_access_token(pasted: str) -> str:
    """Lets the Connect tab's paste field accept either a raw User Access Token (e.g. copied
    from Graph API Explorer) or a full URL containing one — pulls `access_token=...` out of
    a URL if present, else returns the input as-is."""
    pasted = pasted.strip()
    match = re.search(r"access_token=([^&\s]+)", pasted)
    if match:
        return urllib.parse.unquote(match.group(1))
    return pasted


def fetch_pages_with_token(access_token: str, app_id: str, app_secret: str, on_progress=None) -> list[dict]:
    """Given a User Access Token, upgrade it to long-lived when an App ID/Secret is
    available, then return every Page it can manage. Runs off the UI thread."""
    if not access_token:
        raise ValueError("Chưa có access token để kết nối.")

    token = access_token
    if app_id and app_secret:
        if on_progress:
            on_progress("Đang đổi sang token dài hạn...")
        token = FacebookClient.exchange_for_long_lived_token(app_id, app_secret, access_token)
    elif on_progress:
        on_progress("Chưa có App Secret nên bỏ qua bước đổi token dài hạn (token sẽ hết hạn sau ~1-2 giờ).")

    if on_progress:
        on_progress("Đang tải danh sách Page...")
    return FacebookClient.list_pages_for_token(token)
