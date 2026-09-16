"""Turns a local sample video/audio file into text via OpenAI's Whisper transcription API,
so the Video tab can suggest a script/idea "inspired by" a reference clip.

Whisper is OpenAI-only in this app's supported providers, so this always uses the OpenAI
key regardless of which provider (Claude or OpenAI) is chosen for writing the actual script.
mp4/mov/webm are accepted directly — OpenAI extracts the audio server-side, no local ffmpeg
needed.
"""
from __future__ import annotations

from pathlib import Path

from openai import OpenAI

MAX_FILE_SIZE_MB = 25
SAMPLE_FILE_FILTER = "Video/Audio (*.mp4 *.mov *.mkv *.webm *.mp3 *.wav *.m4a)"


class TranscriptionClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError(
                "Thiếu OpenAI API key (dùng để chuyển lời thoại video mẫu thành văn bản). Vào Cài đặt để nhập."
            )
        self.client = OpenAI(api_key=api_key)

    def transcribe(self, file_path: Path) -> str:
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise ValueError(
                f"File mẫu {size_mb:.1f}MB vượt quá giới hạn {MAX_FILE_SIZE_MB}MB của OpenAI Whisper. "
                "Hãy dùng một đoạn video/audio ngắn hơn."
            )
        with open(file_path, "rb") as f:
            transcript = self.client.audio.transcriptions.create(model="whisper-1", file=f)
        text = (transcript.text or "").strip()
        if not text:
            raise RuntimeError("Không nhận diện được lời thoại nào trong file mẫu.")
        return text
