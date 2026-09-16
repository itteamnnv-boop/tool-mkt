"""Wraps Google OAuth (desktop PKCE flow) and the YouTube Data API v3 for video uploads.

Google's "Desktop app" OAuth client type accepts ANY loopback redirect_uri/port at runtime —
unlike TikTok, there is no fixed port to pre-register. See
https://developers.google.com/identity/protocols/oauth2/native-app and
https://developers.google.com/youtube/v3/guides/uploading_a_video.

Caveat: while the OAuth consent screen's Publishing status is "Testing" (the default for a
freshly created Google Cloud project), Google revokes the refresh token after 7 days for
external test users — you'll need to reconnect weekly unless you either keep re-adding
yourself as a Test user, or move Publishing status to "In production" (which removes the
7-day limit but shows an "unverified app" warning during login that you click through, since
it is your own app).
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import mimetypes
import secrets
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
VIDEO_FILE_FILTER = "Video (*.mp4 *.mov *.webm *.avi *.mkv)"

# 8MB per PUT chunk — keeps memory use low regardless of video size, well within Google's
# resumable-upload limits (any multiple of 256KB is valid).
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024

PRIVACY_LABELS = {
    "private": "Riêng tư",
    "unlisted": "Không công khai (có link mới xem được)",
    "public": "Công khai",
}

CATEGORY_LABELS = {
    "22": "Con người & Blog",
    "24": "Giải trí",
    "26": "Hướng dẫn & Phong cách",
    "27": "Giáo dục",
    "28": "Khoa học & Công nghệ",
    "25": "Tin tức & Chính trị",
}


class YouTubeAuthError(RuntimeError):
    pass


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    # Class-level box: the one request that matters (the OAuth redirect) writes its query
    # params here; the polling loop in authorize_and_get_tokens() reads them back.
    result: dict = {}

    def do_GET(self) -> None:  # noqa: N802 - name required by BaseHTTPRequestHandler
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.result = {k: v[0] for k, v in params.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            "<html><body style='font-family:sans-serif;padding:40px;text-align:center;'>"
            "<h2>Đã đăng nhập Google/YouTube — đóng tab này và quay lại ứng dụng.</h2>"
            "</body></html>".encode("utf-8")
        )

    def log_message(self, format, *args):  # noqa: A002 - silence default request logging
        return


def authorize_and_get_tokens(client_id: str, client_secret: str, on_progress=None) -> dict:
    """Runs the full desktop OAuth+PKCE flow: opens the system browser, waits for the
    loopback redirect (bound to an OS-assigned free port — Google needs no pre-registration
    of it), exchanges the code for tokens, then fetches the connected channel's display name.
    Blocking — always run inside a worker thread.

    Returns {"access_token", "refresh_token", "expires_at", "channel_title", "channel_id"}.
    """
    if not client_id or not client_secret:
        raise ValueError("Thiếu YouTube (Google) Client ID/Secret. Vào tab Cài đặt để nhập.")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    _CallbackHandler.result = {}

    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    redirect_uri = f"http://127.0.0.1:{server.server_port}/"
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",  # ask for a refresh_token, not just a short-lived access_token
            "prompt": "consent",  # force the consent screen so a refresh_token is issued every time
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if on_progress:
            on_progress("Đang mở trình duyệt để đăng nhập Google...")
        webbrowser.open(f"{AUTH_URL}?{urllib.parse.urlencode(params)}")

        if on_progress:
            on_progress("Đang chờ bạn đăng nhập/đồng ý trong trình duyệt (tối đa 3 phút)...")
        deadline = time.time() + 180
        while not _CallbackHandler.result and time.time() < deadline:
            time.sleep(0.3)
    finally:
        server.shutdown()
        server_thread.join(timeout=5)

    result = _CallbackHandler.result
    if not result:
        raise YouTubeAuthError("Hết thời gian chờ đăng nhập Google. Vui lòng thử lại.")
    if "error" in result:
        raise YouTubeAuthError(f"Google từ chối đăng nhập: {result.get('error_description', result['error'])}")
    if result.get("state") != state:
        raise YouTubeAuthError("Phản hồi đăng nhập không hợp lệ (state không khớp) — vui lòng thử lại.")
    code = result.get("code")
    if not code:
        raise YouTubeAuthError("Không nhận được mã xác thực (code) từ Google.")

    if on_progress:
        on_progress("Đang đổi mã xác thực lấy access token...")
    tokens = exchange_code_for_token(client_id, client_secret, code, verifier, redirect_uri)

    try:
        channel = YouTubeClient(tokens["access_token"]).get_own_channel()
        tokens["channel_title"] = channel.get("title", "")
        tokens["channel_id"] = channel.get("id", "")
    except Exception:  # noqa: BLE001 - a failed nice-to-have info fetch must not break login
        tokens["channel_title"] = ""
        tokens["channel_id"] = ""
    return tokens


def exchange_code_for_token(
    client_id: str, client_secret: str, code: str, code_verifier: str, redirect_uri: str
) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    return _parse_token_response(resp)


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    return _parse_token_response(resp)


def _parse_token_response(resp: requests.Response) -> dict:
    _raise_for_status(resp)
    data = resp.json()
    if "error" in data:
        raise YouTubeAuthError(f"Google OAuth lỗi: {data.get('error_description', data['error'])}")
    if not data.get("access_token"):
        raise YouTubeAuthError(f"Google không trả về access_token: {data}")
    return {
        "access_token": data["access_token"],
        # Google only returns refresh_token on first consent (prompt=consent above forces this
        # every time) — a plain refresh call never returns a new one, so callers must keep the
        # previous refresh_token around rather than expecting a fresh one here.
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": time.time() + int(data.get("expires_in", 0)),
    }


def _raise_for_status(resp: requests.Response) -> None:
    if resp.ok:
        return
    try:
        detail = resp.json()
    except ValueError:
        detail = resp.text
    raise RuntimeError(f"YouTube/Google API lỗi ({resp.status_code}): {detail}")


class YouTubeClient:
    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("Chưa kết nối tài khoản YouTube. Vào tab 'Kết nối YouTube' trước.")
        self.access_token = access_token

    def _headers(self, **extra: str) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", **extra}

    def get_own_channel(self) -> dict:
        resp = requests.get(
            CHANNELS_URL, headers=self._headers(), params={"part": "snippet", "mine": "true"}, timeout=30
        )
        _raise_for_status(resp)
        items = resp.json().get("items", [])
        if not items:
            return {}
        return {"id": items[0].get("id", ""), "title": items[0].get("snippet", {}).get("title", "")}

    def _init_resumable_upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        category_id: str,
        privacy_status: str,
    ) -> str:
        content_type = mimetypes.guess_type(str(video_path))[0] or "video/mp4"
        body = {
            "snippet": {
                "title": title or video_path.stem,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {"privacyStatus": privacy_status},
        }
        resp = requests.post(
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers=self._headers(
                **{
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Length": str(video_path.stat().st_size),
                    "X-Upload-Content-Type": content_type,
                }
            ),
            json=body,
            timeout=30,
        )
        _raise_for_status(resp)
        upload_url = resp.headers.get("Location")
        if not upload_url:
            raise RuntimeError("Google không trả về upload URL (thiếu header Location).")
        return upload_url

    @staticmethod
    def _upload_video_bytes(upload_url: str, video_path: Path, on_progress=None) -> dict:
        content_type = mimetypes.guess_type(str(video_path))[0] or "video/mp4"
        total_size = video_path.stat().st_size
        with open(video_path, "rb") as f:
            start = 0
            while start < total_size:
                chunk = f.read(UPLOAD_CHUNK_SIZE)
                end = start + len(chunk) - 1
                if on_progress:
                    percent = int((end + 1) / total_size * 100)
                    on_progress(f"Đang tải video lên YouTube... ({percent}%)")
                resp = requests.put(
                    upload_url,
                    data=chunk,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{total_size}",
                        "Content-Type": content_type,
                    },
                    timeout=180,
                )
                if resp.status_code in (200, 201):
                    return resp.json()
                if resp.status_code == 308:
                    start = end + 1
                    continue
                raise RuntimeError(f"YouTube tải video lên thất bại ({resp.status_code}): {resp.text}")
        raise RuntimeError("Tải video lên YouTube kết thúc bất thường (không nhận được phản hồi hoàn tất).")

    def upload_video(
        self,
        video_path: Path,
        title: str = "",
        description: str = "",
        tags: list[str] | None = None,
        category_id: str = "22",
        privacy_status: str = "private",
        on_progress=None,
    ) -> dict:
        if on_progress:
            on_progress("Đang khởi tạo phiên tải video lên YouTube...")
        upload_url = self._init_resumable_upload(
            video_path, title, description, tags or [], category_id, privacy_status
        )
        return self._upload_video_bytes(upload_url, video_path, on_progress=on_progress)
