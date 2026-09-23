"""Wraps the HeyGen v2 API: avatar/voice lookup and talking-avatar video generation."""
from __future__ import annotations

import time
from pathlib import Path

import requests

BASE_URL = "https://api.heygen.com"


class GenerationCancelled(RuntimeError):
    """Raised when a cancel_event is set while waiting for HeyGen to render a video.

    The `is_cancelled` marker lets Worker (app/workers/async_worker.py) tell this apart
    from a real failure without either module importing from the other — it just reports
    a deliberate stop instead of an error. Note this only stops the app from waiting/polling
    locally; HeyGen has no documented API to cancel a render already in progress server-side.
    """

    is_cancelled = True


class HeyGenClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Thiếu HeyGen API key. Vào Cài đặt để nhập.")
        self.api_key = api_key
        self.headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = requests.get(f"{BASE_URL}{path}", headers=self.headers, params=params, timeout=30)
        self._raise_for_status(resp)
        return resp.json()

    def _post(self, path: str, json_body: dict) -> dict:
        resp = requests.post(f"{BASE_URL}{path}", headers=self.headers, json=json_body, timeout=30)
        self._raise_for_status(resp)
        return resp.json()

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        if resp.ok:
            return
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"HeyGen API lỗi ({resp.status_code}): {detail}")

    def list_avatars(self) -> list[dict]:
        """Return only this account's avatar looks, using the existing UI keys."""
        rows = self._list_private("/v3/avatars/looks", {"ownership": "private", "limit": 50})
        return [dict(row, avatar_id=row["id"], avatar_name=row.get("name") or row["id"])
                for row in rows if row.get("id")]

    def list_voices(self) -> list[dict]:
        """Return My Voices only; never fall back to the public library."""
        return self._list_private("/v3/voices", {"type": "private", "limit": 100})

    def _list_private(self, path: str, filters: dict) -> list[dict]:
        rows = []
        params = dict(filters)
        seen_tokens = set()
        while True:
            page = self._get(path, params=params.copy())
            data = page.get("data")
            if not isinstance(data, list):
                raise RuntimeError("HeyGen trả về danh sách cá nhân không hợp lệ.")
            rows.extend(data)
            if not page.get("has_more"):
                return rows
            token = page.get("next_token")
            if not token or token in seen_tokens:
                raise RuntimeError("Không thể tải đủ danh sách cá nhân từ HeyGen. Hãy thử lại.")
            seen_tokens.add(token)
            params["token"] = token

    def generate_video(
        self,
        avatar_id: str,
        voice_id: str,
        script_text: str,
        width: int = 1280,
        height: int = 720,
    ) -> str:
        if not avatar_id or not voice_id:
            raise ValueError("Cần chọn Avatar và Voice trước khi tạo video.")
        if not script_text.strip():
            raise ValueError("Kịch bản (script) không được để trống.")

        body = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "avatar_style": "normal",
                    },
                    "voice": {
                        "type": "text",
                        "input_text": script_text,
                        "voice_id": voice_id,
                    },
                }
            ],
            "dimension": {"width": width, "height": height},
        }
        data = self._post("/v2/video/generate", body)
        video_id = data.get("data", {}).get("video_id")
        if not video_id:
            raise RuntimeError(f"HeyGen không trả về video_id: {data}")
        return video_id

    def get_status(self, video_id: str) -> dict:
        data = self._get("/v1/video_status.get", params={"video_id": video_id})
        return data.get("data", {})

    def wait_for_completion(
        self,
        video_id: str,
        poll_interval: float = 5.0,
        timeout: float = 900.0,
        on_progress=None,
        on_thumbnail=None,
        cancel_event=None,
    ) -> str:
        def check_cancelled() -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelled("Đã huỷ tạo video theo yêu cầu.")

        start = time.time()
        thumbnail_seen = False
        while time.time() - start < timeout:
            check_cancelled()
            status = self.get_status(video_id)
            state = status.get("status")
            if on_progress:
                on_progress(state or "unknown")
            thumbnail_url = status.get("thumbnail_url")
            if on_thumbnail and thumbnail_url and not thumbnail_seen:
                # HeyGen sometimes exposes a preview frame before the video itself is ready —
                # show it as soon as it appears instead of waiting for full completion.
                on_thumbnail(thumbnail_url)
                thumbnail_seen = True
            if state == "completed":
                video_url = status.get("video_url")
                if not video_url:
                    raise RuntimeError("HeyGen báo completed nhưng không có video_url.")
                return video_url
            if state == "failed":
                raise RuntimeError(f"HeyGen tạo video thất bại: {status.get('error')}")
            # Sleep in short slices so a cancel request takes effect quickly instead of
            # waiting out the rest of a (default 5s) poll interval.
            slept = 0.0
            while slept < poll_interval:
                check_cancelled()
                step = min(0.5, poll_interval - slept)
                time.sleep(step)
                slept += step
        raise TimeoutError("Hết thời gian chờ HeyGen tạo video.")

    def generate_and_wait(
        self,
        avatar_id: str,
        voice_id: str,
        script_text: str,
        dest_dir: Path,
        on_progress=None,
        on_thumbnail=None,
        cancel_event=None,
    ) -> Path:
        """Convenience wrapper: create the video, poll until done, download it. Runs in a worker thread."""
        if on_progress:
            on_progress("Đang gửi yêu cầu tạo video tới HeyGen...")
        video_id = self.generate_video(avatar_id, voice_id, script_text)
        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelled("Đã huỷ tạo video theo yêu cầu.")
        if on_progress:
            on_progress(f"Đã tạo video_id={video_id}, đang chờ xử lý...")
        video_url = self.wait_for_completion(
            video_id, on_progress=on_progress, on_thumbnail=on_thumbnail, cancel_event=cancel_event
        )
        if on_progress:
            on_progress("Đang tải video về máy...")
        return self.download(video_url, dest_dir)

    def generate_from_prompt_and_wait(self, avatar_id: str, voice_id: str, script_text: str,
                                     prompt: str, dest_dir: Path, on_progress=None,
                                     on_thumbnail=None, cancel_event=None, timeout: float = 900) -> Path:
        """Video Agent applies visual directions while retaining the chosen identity.

        Reference: https://developers.heygen.com/docs/video-agent
        """
        if not avatar_id or not voice_id or not script_text.strip():
            raise ValueError("Cần chọn Avatar, Voice và nhập kịch bản.")
        if not 1 <= len(prompt.strip()) <= 10000:
            raise ValueError("Prompt HeyGen cần từ 1 đến 10.000 ký tự (bao gồm kịch bản).")

        def check_cancelled():
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelled("Đã dừng chờ Video Agent; tác vụ trên HeyGen có thể vẫn tiếp tục.")

        check_cancelled()
        response = self._post("/v3/video-agents", {
            "prompt": prompt, "mode": "generate", "avatar_id": avatar_id, "voice_id": voice_id,
        }).get("data", {})
        session_id = response.get("session_id")
        if not session_id:
            raise RuntimeError("HeyGen không trả về session_id cho Video Agent.")
        deadline = time.monotonic() + timeout
        video_id = response.get("video_id")
        while time.monotonic() < deadline:
            check_cancelled()
            session = self._get(f"/v3/video-agents/{session_id}").get("data", {})
            if session.get("status") in {"failed", "cancelled", "stopped"}:
                raise RuntimeError(f"Video Agent thất bại: {session.get('error') or session.get('status')}")
            video_id = session.get("video_id") or video_id
            if on_progress:
                on_progress(f"HeyGen Video Agent: {session.get('status', 'generating')}")
            if video_id:
                video = self._get(f"/v3/videos/{video_id}").get("data", {})
                if video.get("status") == "failed":
                    raise RuntimeError(f"HeyGen tạo video thất bại: {video.get('error')}")
                if video.get("status") == "completed":
                    url = video.get("video_url")
                    if not url:
                        raise RuntimeError("HeyGen báo hoàn tất nhưng chưa trả về video_url.")
                    check_cancelled()
                    return self.download(url, dest_dir)
            if cancel_event is not None:
                cancel_event.wait(10)
            else:
                time.sleep(10)
        raise TimeoutError("Hết thời gian chờ HeyGen Video Agent tạo video.")

    @staticmethod
    def download(video_url: str, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"video_{int(time.time())}.mp4"
        resp = requests.get(video_url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
        return dest_path
