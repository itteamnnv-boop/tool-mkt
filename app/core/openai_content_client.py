"""Wraps the OpenAI chat completion API for content generation (alternative to Claude)."""
from __future__ import annotations

from openai import OpenAI

from app.storage import history_store

from app.core.content_prompts import (
    SYSTEM_PROMPT_IMAGE_PROMPT,
    get_post_system_prompt,
    SYSTEM_PROMPT_VIDEO_SCRIPT,
    SYSTEM_PROMPT_VIDEO_SCRIPT_FROM_REFERENCE,
    build_image_prompt_user_prompt,
    build_post_user_prompt,
    build_video_script_from_reference_user_prompt,
    build_video_script_user_prompt,
)


class OpenAIContentClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            raise ValueError("Thiếu OpenAI API key. Vào Cài đặt để nhập.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _complete(self, system: str, user: str, max_tokens: int = 1024, operation: str = "content") -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        usage = response.usage
        if usage:
            history_store.add_token_usage("OpenAI", self.model, operation, usage.prompt_tokens, usage.completion_tokens)
        return (response.choices[0].message.content or "").strip()

    def generate_post(
        self,
        topic: str,
        tone: str = "thân thiện, chuyên nghiệp",
        length: str = "trung bình (80-150 từ)",
        audience: str = "khách hàng đại chúng",
        include_hashtags: bool = True,
        system_prompt: str | None = None,
    ) -> str:
        user_prompt = build_post_user_prompt(topic, tone, length, audience, include_hashtags)
        return self._complete(get_post_system_prompt() if system_prompt is None else system_prompt, user_prompt, operation="content")

    def suggest_image_prompt(self, content_text: str) -> str:
        return self._complete(
            SYSTEM_PROMPT_IMAGE_PROMPT, build_image_prompt_user_prompt(content_text), max_tokens=200, operation="prompt ảnh"
        )

    def suggest_video_script(self, content_text: str) -> str:
        return self._complete(
            SYSTEM_PROMPT_VIDEO_SCRIPT, build_video_script_user_prompt(content_text), max_tokens=400, operation="kịch bản video"
        )

    def suggest_video_script_from_reference(self, transcript: str, content_text: str = "") -> str:
        return self._complete(
            SYSTEM_PROMPT_VIDEO_SCRIPT_FROM_REFERENCE,
            build_video_script_from_reference_user_prompt(transcript, content_text),
            max_tokens=400,
            operation="kịch bản video từ mẫu",
        )
