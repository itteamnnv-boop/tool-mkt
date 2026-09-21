"""Wraps the OpenAI image generation API."""
from __future__ import annotations

import base64
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

    def generate_image(self, prompt: str, size: str, dest_dir: Path) -> Path:
        if not prompt.strip():
            raise ValueError("Prompt tạo ảnh không được để trống.")
        response = self.client.images.generate(
            model=self.model,
            prompt=prompt,
            size=size,
            n=1,
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
