"""Wraps the OpenAI image generation API."""
from __future__ import annotations

import base64
from contextlib import ExitStack
import time
from uuid import uuid4
from pathlib import Path

import requests
from openai import OpenAI

from app.storage import history_store


class ImageClient:
    def __init__(self, api_key: str, model: str = "gpt-image-1"):
        if not api_key:
            raise ValueError("Thiếu OpenAI API key. Vào Cài đặt để nhập.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    @staticmethod
    def validate_reference_image(path: Path) -> None:
        if not path.is_file():
            raise ValueError("Không tìm thấy hình mẫu. Hãy chọn lại ảnh.")
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("Hình mẫu cần có định dạng PNG, JPG hoặc WebP.")
        if not 0 < path.stat().st_size < 50 * 1024 * 1024:
            raise ValueError("Hình mẫu phải có dữ liệu và nhỏ hơn 50 MB.")

    def generate_image(
        self, prompt: str, size: str, dest_dir: Path,
        reference_image_path: Path | None = None,
        face_image_path: Path | None = None,
        mask_path: Path | None = None,
        product_image_path: Path | None = None,
    ) -> Path:
        if not prompt.strip():
            raise ValueError("Prompt tạo ảnh không được để trống.")
        # Keep the face first, matching the numbered image roles in the prompt.
        input_paths = [path for path in (face_image_path, reference_image_path) if path is not None]
        if product_image_path is not None:
            input_paths.append(product_image_path)
        if mask_path is not None:
            if reference_image_path is None:
                raise ValueError("Chỉnh sửa theo vùng cần ảnh gốc.")
            if not mask_path.is_file() or mask_path.suffix.lower() != ".png" or not 0 < mask_path.stat().st_size < 4 * 1024 * 1024:
                raise ValueError("Vùng chỉnh sửa phải là ảnh PNG nhỏ hơn 4 MB.")
            # Masks apply to the first image, so the edit target must precede the face.
            input_paths = [reference_image_path] + ([face_image_path] if face_image_path else [])
            if product_image_path is not None:
                input_paths.append(product_image_path)
        if input_paths:
            for path in input_paths:
                self.validate_reference_image(path)
            if not (self.model.startswith("gpt-image-") or self.model == "chatgpt-image-latest"):
                raise ValueError("Tạo vật liệu từ hình mẫu cần model GPT Image. Hãy chọn gpt-image-1 trong Cài đặt.")
            with ExitStack() as stack:
                # Explicit MIME types avoid OS/registry-dependent filename guessing,
                # especially WebP uploads on Windows.
                mime_types = {".png": "image/png", ".jpg": "image/jpeg",
                              ".jpeg": "image/jpeg", ".webp": "image/webp"}
                image_files = [
                    (path.name, stack.enter_context(path.open("rb")), mime_types[path.suffix.lower()])
                    for path in input_paths
                ]
                mask_args = {"mask": (mask_path.name, stack.enter_context(mask_path.open("rb")), "image/png")} if mask_path else {}
                response = self.client.images.edit(
                    model=self.model, image=image_files if len(image_files) > 1 else image_files[0],
                    prompt=prompt, size=size, n=1, **mask_args,
                )
        else:
            response = self.client.images.generate(
                model=self.model, prompt=prompt, size=size, n=1,
            )
        usage = getattr(response, "usage", None)
        if usage:
            history_store.add_token_usage(
                "OpenAI", self.model, "tạo ảnh",
                getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)),
                getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)),
            )
        item = response.data[0]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"image_{int(time.time())}_{uuid4().hex[:10]}.png"

        b64_data = getattr(item, "b64_json", None)
        if b64_data:
            dest_path.write_bytes(base64.b64decode(b64_data))
        elif getattr(item, "url", None):
            resp = requests.get(item.url, timeout=60)
            resp.raise_for_status()
            dest_path.write_bytes(resp.content)
        else:
            raise RuntimeError("OpenAI không trả về dữ liệu ảnh hợp lệ.")

        return dest_path
