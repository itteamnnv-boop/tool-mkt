"""Wraps TikTok's OAuth (desktop PKCE flow) and Content Posting API (Direct Post, video only).

TikTok Login Kit has no self-serve "paste a token" playground like Facebook's Graph API
Explorer — a desktop app must register a fixed loopback redirect URI in its own TikTok
Developer app and complete a real OAuth 2.0 + PKCE exchange. See
https://developers.tiktok.com/doc/login-kit-desktop and
https://developers.tiktok.com/doc/content-posting-api-get-started.

Until the TikTok app passes review ("audit"), every post is forced to private (SELF_ONLY)
viewing regardless of the privacy_level requested — this is a TikTok-side restriction, not a
bug here.
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

API_BASE = "https://open.tiktokapis.com"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
REDIRECT_PORT = 5577
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback/"  # TikTok's UI rejects the "localhost" hostname
SCOPES = "user.info.basic,video.publish"
VIDEO_FILE_FILTER = "Video (*.mp4 *.mov *.webm)"

# TikTok's chunked-upload rule: each chunk must be 5-64MB (last chunk may be bigger, up to
# 128MB) — files at or under this size upload as a single PUT with no chunking needed.
SINGLE_CHUNK_MAX_BYTES = 64 * 1024 * 1024

PRIVACY_LABELS = {
    "PUBLIC_TO_EVERYONE": "Công khai",
    "MUTUAL_FOLLOW_FRIENDS": "Bạn bè theo dõi lẫn nhau",
    "FOLLOWER_OF_CREATOR": "Người theo dõi",
    "SELF_ONLY": "Chỉ mình tôi (riêng tư)",
}


class TikTokAuthError(RuntimeError):
    pass


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    # TikTok deviates from RFC 7636 here: most providers base64url-encode the SHA256 digest for
    # code_challenge, but TikTok's own docs/example (developers.tiktok.com/doc/login-kit-desktop)
    # hex-encode it instead — using base64url like everywhere else makes every token exchange
    # fail with "Code verifier or code challenge is invalid".
    challenge = hashlib.sha256(verifier.encode("ascii")).hexdigest()
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    # Class-level box: the one request that matters (the OAuth redirect) writes its query
    # params here; the polling loop in authorize_and_get_tokens() reads them back.
    result: dict = {}

    def do_GET(self) -> None:  # noqa: N802 - name required by BaseHTTPRequestHandler
        parsed = urllib.parse.urlparse(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if parsed.path.rstrip("/") == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            _CallbackHandler.result = {k: v[0] for k, v in params.items()}
            self.wfile.write(
                "<html><body style='font-family:sans-serif;padding:40px;text-align:center;'>"
                "<h2>Đã đăng nhập TikTok — đóng tab này và quay lại ứng dụng.</h2>"
                "</body></html>".encode("utf-8")
            )

    def log_message(self, format, *args):  # noqa: A002 - silence default request logging
        return


def authorize_and_get_tokens(client_key: str, client_secret: str, on_progress=None) -> dict:
    """Runs the full desktop OAuth+PKCE flow: opens the system browser, waits for the
    loopback redirect, exchanges the code for tokens, then fetches creator display info.
    Blocking — always run inside a worker thread.

    Returns {"access_token", "refresh_token", "expires_at", "open_id", "display_name", "avatar_url"}.
    """
    if not client_key or not client_secret:
        raise ValueError("Thiếu TikTok Client Key/Secret. Vào tab Cài đặt để nhập.")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    _CallbackHandler.result = {}

    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        params = {
            "client_key": client_key,
            "scope": SCOPES,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if on_progress:
            on_progress("Đang mở trình duyệt để đăng nhập TikTok...")
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
        raise TikTokAuthError("Hết thời gian chờ đăng nhập TikTok. Vui lòng thử lại.")
    if "error" in result:
        raise TikTokAuthError(f"TikTok từ chối đăng nhập: {result.get('error_description', result['error'])}")
    if result.get("state") != state:
        raise TikTokAuthError("Phản hồi đăng nhập không hợp lệ (state không khớp) — vui lòng thử lại.")
    code = result.get("code")
    if not code:
        raise TikTokAuthError("Không nhận được mã xác thực (code) từ TikTok.")

    if on_progress:
        on_progress("Đang đổi mã xác thực lấy access token...")
    tokens = exchange_code_for_token(client_key, client_secret, code, verifier)

    try:
        creator = TikTokClient(tokens["access_token"]).query_creator_info()
        tokens["display_name"] = creator.get("creator_nickname", "")
        tokens["avatar_url"] = creator.get("creator_avatar_url", "")
    except Exception:  # noqa: BLE001 - a failed nice-to-have info fetch must not break login
        tokens["display_name"] = ""
        tokens["avatar_url"] = ""
    return tokens


def exchange_code_for_token(client_key: str, client_secret: str, code: str, code_verifier: str) -> dict:
    resp = requests.post(
        f"{API_BASE}/v2/oauth/token/",
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    return _parse_token_response(resp)


def refresh_access_token(client_key: str, client_secret: str, refresh_token: str) -> dict:
    resp = requests.post(
        f"{API_BASE}/v2/oauth/token/",
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    return _parse_token_response(resp)


def _parse_token_response(resp: requests.Response) -> dict:
    _raise_for_status(resp)
    data = resp.json()
    if data.get("error"):
        raise TikTokAuthError(f"TikTok OAuth lỗi: {data.get('error_description', data['error'])}")
    if not data.get("access_token"):
        raise TikTokAuthError(f"TikTok không trả về access_token: {data}")
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": time.time() + int(data.get("expires_in", 0)),
        "open_id": data.get("open_id", ""),
    }


def _raise_for_status(resp: requests.Response) -> None:
    if resp.ok:
        return
    try:
        detail = resp.json()
    except ValueError:
        detail = resp.text
    raise RuntimeError(f"TikTok API lỗi ({resp.status_code}): {detail}")


class TikTokClient:
    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("Chưa kết nối tài khoản TikTok. Vào tab 'Kết nối TikTok' trước.")
        self.access_token = access_token

    def _post(self, path: str, json_body: dict) -> dict:
        resp = requests.post(
            f"{API_BASE}{path}",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json=json_body,
            timeout=30,
        )
        _raise_for_status(resp)
        data = resp.json()
        error = data.get("error") or {}
        if error.get("code") not in (None, "ok"):
            raise RuntimeError(f"TikTok API lỗi: {error.get('message') or error}")
        return data

    def query_creator_info(self) -> dict:
        return self._post("/v2/post/publish/creator_info/query/", {}).get("data", {})

    def init_video_post(
        self,
        video_size: int,
        privacy_level: str,
        title: str = "",
        disable_duet: bool = False,
        disable_comment: bool = False,
        disable_stitch: bool = False,
    ) -> tuple[str, str, int, int]:
        chunk_size = min(video_size, SINGLE_CHUNK_MAX_BYTES)
        total_chunk_count = max(1, -(-video_size // chunk_size))  # ceil division
        body = {
            "post_info": {
                "title": title,
                "privacy_level": privacy_level,
                "disable_duet": disable_duet,
                "disable_comment": disable_comment,
                "disable_stitch": disable_stitch,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            },
        }
        data = self._post("/v2/post/publish/video/init/", body).get("data", {})
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        if not publish_id or not upload_url:
            raise RuntimeError(f"TikTok không trả về publish_id/upload_url: {data}")
        return publish_id, upload_url, chunk_size, total_chunk_count

    @staticmethod
    def upload_video_chunks(
        upload_url: str, video_path: Path, chunk_size: int, total_chunk_count: int, on_progress=None
    ) -> None:
        content_type = mimetypes.guess_type(str(video_path))[0] or "video/mp4"
        total_size = video_path.stat().st_size
        with open(video_path, "rb") as f:
            for chunk_index in range(total_chunk_count):
                start = chunk_index * chunk_size
                is_last = chunk_index == total_chunk_count - 1
                end = total_size - 1 if is_last else start + chunk_size - 1
                length = end - start + 1
                chunk = f.read(length)
                if on_progress:
                    on_progress(f"Đang tải video lên TikTok... (phần {chunk_index + 1}/{total_chunk_count})")
                resp = requests.put(
                    upload_url,
                    data=chunk,
                    headers={
                        "Content-Type": content_type,
                        "Content-Length": str(length),
                        "Content-Range": f"bytes {start}-{end}/{total_size}",
                    },
                    timeout=180,
                )
                if resp.status_code not in (200, 201, 206):
                    raise RuntimeError(f"TikTok tải video lên thất bại ({resp.status_code}): {resp.text}")

    def get_publish_status(self, publish_id: str) -> dict:
        return self._post("/v2/post/publish/status/fetch/", {"publish_id": publish_id}).get("data", {})

    def wait_for_publish(
        self, publish_id: str, poll_interval: float = 3.0, timeout: float = 300.0, on_progress=None
    ) -> dict:
        start = time.time()
        while time.time() - start < timeout:
            status = self.get_publish_status(publish_id)
            state = status.get("status")
            if on_progress:
                on_progress(f"Trạng thái đăng TikTok: {state}")
            if state == "PUBLISH_COMPLETE":
                return status
            if state == "FAILED":
                raise RuntimeError(f"TikTok báo đăng thất bại: {status.get('fail_reason', status)}")
            time.sleep(poll_interval)
        raise TimeoutError("Hết thời gian chờ TikTok xử lý bài đăng.")

    def post_video(
        self,
        video_path: Path,
        title: str = "",
        privacy_level: str = "SELF_ONLY",
        disable_duet: bool = False,
        disable_comment: bool = False,
        disable_stitch: bool = False,
        on_progress=None,
    ) -> dict:
        video_size = video_path.stat().st_size
        if on_progress:
            on_progress("Đang khởi tạo bài đăng TikTok...")
        publish_id, upload_url, chunk_size, total_chunk_count = self.init_video_post(
            video_size, privacy_level, title, disable_duet, disable_comment, disable_stitch
        )
        self.upload_video_chunks(upload_url, video_path, chunk_size, total_chunk_count, on_progress=on_progress)
        if on_progress:
            on_progress("Đã tải video xong, đang chờ TikTok xử lý...")
        return self.wait_for_publish(publish_id, on_progress=on_progress)
