"""Wraps xAI's Grok video generation API (text-to-video, no avatar/voice needed)."""
from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path

import requests

BASE_URL = "https://api.x.ai"
DEFAULT_MODEL = "grok-imagine-video-1.5"

ASPECT_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3"]
RESOLUTIONS = ["480p", "720p", "1080p"]
IMAGE_FILE_FILTER = "Ảnh (*.png *.jpg *.jpeg *.webp)"
MAX_REFERENCE_IMAGES = 4


def image_to_data_uri(image_path: Path) -> str:
    """Encode a local image as a data URI, the format xAI's `image` field accepts
    alongside a public URL or file_id (see docs.x.ai/developers/model-capabilities/video)."""
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type or not mime_type.startswith("image/"):
        raise ValueError(f"Định dạng ảnh không được hỗ trợ: {image_path.suffix}")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class GenerationCancelled(RuntimeError):
    """Raised when a cancel_event is set while waiting for Grok to render a video.

    Mirrors HeyGenClient.GenerationCancelled (see app/core/heygen_client.py) so
    Worker (app/workers/async_worker.py) treats a deliberate stop the same way for
    either video provider, without the two client modules importing each other.
    """

    is_cancelled = True


class GrokVideoClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Thiếu Grok (xAI) API key. Vào Cài đặt để nhập.")
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def _get(self, path: str) -> dict:
        resp = requests.get(f"{BASE_URL}{path}", headers=self.headers, timeout=30)
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
        raise RuntimeError(f"Grok (xAI) API lỗi ({resp.status_code}): {detail}")

    def list_models(self) -> list[dict]:
        """Lightweight call used only to verify the API key works (no video is generated)."""
        data = self._get("/v1/models")
        return data.get("data", [])

    def generate_video(
        self,
        prompt: str,
        duration: int = 6,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        model: str = DEFAULT_MODEL,
        image_path: Path | None = None,
        reference_image_paths: list[Path] | None = None,
    ) -> str:
        if not prompt.strip():
            raise ValueError("Mô tả video (prompt) không được để trống.")
        if reference_image_paths and len(reference_image_paths) > MAX_REFERENCE_IMAGES:
            raise ValueError(f"Chỉ được đính kèm tối đa {MAX_REFERENCE_IMAGES} ảnh vật liệu tham chiếu.")
        body = {
            "model": model,
            "prompt": prompt,
            "duration": max(1, min(15, duration)),
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }
        if image_path is not None:
            # Image-to-video: Grok animates this exact image as the starting frame.
            body["image"] = {"url": image_to_data_uri(image_path)}
        if reference_image_paths:
            # Reference-to-video: extra materials (e.g. a face photo) that guide style/character
            # consistency without pinning any single frame — can be combined with `image` above.
            body["reference_images"] = [{"url": image_to_data_uri(p)} for p in reference_image_paths]
        data = self._post("/v1/videos/generations", body)
        request_id = data.get("request_id")
        if not request_id:
            raise RuntimeError(f"Grok không trả về request_id: {data}")
        return request_id

    def get_status(self, request_id: str) -> dict:
        return self._get(f"/v1/videos/{request_id}")

    def wait_for_completion(
        self,
        request_id: str,
        poll_interval: float = 5.0,
        timeout: float = 900.0,
        on_progress=None,
        cancel_event=None,
    ) -> str:
        def check_cancelled() -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelled("Đã huỷ tạo video theo yêu cầu.")

        start = time.time()
        while time.time() - start < timeout:
            check_cancelled()
            status = self.get_status(request_id)
            state = status.get("status")
            if on_progress:
                on_progress(state or "unknown")
            if state == "done":
                video_url = (status.get("video") or {}).get("url")
                if not video_url:
                    raise RuntimeError("Grok báo done nhưng không có video url.")
                return video_url
            if state == "failed":
                error = status.get("error") or {}
                raise RuntimeError(f"Grok tạo video thất bại: {error.get('message', error)}")
            if state == "expired":
                raise RuntimeError("Grok báo request đã hết hạn trước khi hoàn tất.")
            # Sleep in short slices so a cancel request takes effect quickly instead of
            # waiting out the rest of a (default 5s) poll interval.
            slept = 0.0
            while slept < poll_interval:
                check_cancelled()
                step = min(0.5, poll_interval - slept)
                time.sleep(step)
                slept += step
        raise TimeoutError("Hết thời gian chờ Grok tạo video.")

    def generate_and_wait(
        self,
        prompt: str,
        dest_dir: Path,
        duration: int = 6,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        image_path: Path | None = None,
        reference_image_paths: list[Path] | None = None,
        on_progress=None,
        cancel_event=None,
    ) -> Path:
        """Convenience wrapper: create the video, poll until done, download it. Runs in a worker thread."""
        if on_progress:
            if image_path is not None or reference_image_paths:
                on_progress("Đang gửi vật liệu (ảnh) và yêu cầu tạo video tới Grok...")
            else:
                on_progress("Đang gửi yêu cầu tạo video tới Grok...")
        request_id = self.generate_video(
            prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            image_path=image_path,
            reference_image_paths=reference_image_paths,
        )
        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelled("Đã huỷ tạo video theo yêu cầu.")
        if on_progress:
            on_progress(f"Đã tạo request_id={request_id}, đang chờ xử lý...")
        video_url = self.wait_for_completion(request_id, on_progress=on_progress, cancel_event=cancel_event)
        if on_progress:
            on_progress("Đang tải video về máy...")
        return self.download(video_url, dest_dir)

    @staticmethod
    def download(video_url: str, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"grok_video_{int(time.time())}.mp4"
        resp = requests.get(video_url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
        return dest_path
