"""Wraps the Facebook Graph API for posting text/photo/video to a Page."""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

import requests

GRAPH_URL = "https://graph.facebook.com/v19.0"


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
        params = {"message": message, "access_token": self.token}
        if link:
            params["link"] = link
        if scheduled_time:
            params["published"] = "false"
            params["scheduled_publish_time"] = scheduled_time
        resp = requests.post(f"{GRAPH_URL}/{self.page_id}/feed", data=params, timeout=60)
        self._raise_for_status(resp)
        return resp.json()

    def post_photo(self, image_path: Path, caption: str = "", scheduled_time: int | None = None) -> dict:
        params = {"caption": caption, "access_token": self.token}
        if scheduled_time:
            params["published"] = "false"
            params["scheduled_publish_time"] = scheduled_time
        with open(image_path, "rb") as f:
            files = {"source": (image_path.name, f, "application/octet-stream")}
            resp = requests.post(f"{GRAPH_URL}/{self.page_id}/photos", data=params, files=files, timeout=180)
        self._raise_for_status(resp)
        return resp.json()

    def post_video(self, video_path: Path, description: str = "", scheduled_time: int | None = None) -> dict:
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
    results = []
    total = len(pages)
    for idx, page in enumerate(pages, start=1):
        if on_progress:
            on_progress(f"Đang đăng lên '{page['name']}' ({idx}/{total})...")
        try:
            client = FacebookClient(page["id"], page["token"])
            if post_type == "photo":
                data = client.post_photo(**kwargs)
            elif post_type == "video":
                data = client.post_video(**kwargs)
            else:
                data = client.post_text(**kwargs)
            results.append(
                {"id": page["id"], "name": page["name"], "ok": True, "post_id": data.get("id") or data.get("post_id", "")}
            )
        except Exception as exc:  # noqa: BLE001 - one page's failure must not abort the rest
            results.append({"id": page["id"], "name": page["name"], "ok": False, "error": str(exc)})
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
