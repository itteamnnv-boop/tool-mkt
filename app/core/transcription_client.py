"""Turns a local sample video/audio file into text via OpenAI's Whisper transcription API,
so the Video tab can suggest a script/idea "inspired by" a reference clip.

Whisper is OpenAI-only in this app's supported providers, so this always uses the OpenAI
key regardless of which provider (Claude or OpenAI) is chosen for writing the actual script.
Reference media is converted to compact audio segments before upload.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import imageio_ffmpeg

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
        if not file_path.is_file():
            raise ValueError("Không tìm thấy video/audio mẫu. Hãy chọn lại tệp.")
        with TemporaryDirectory(prefix="studio-reference-") as folder:
            # Mono 16 kHz / 48 kbps: each ten-minute segment is about 3.6 MB.
            # Splitting preserves the whole recording rather than silently truncating it.
            command = [
                imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error",
                "-i", str(file_path.resolve()), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "libmp3lame", "-b:a", "48k", "-f", "segment", "-segment_time", "600",
                "-reset_timestamps", "1", str(Path(folder) / "audio-%05d.mp3"),
            ]
            try:
                result = subprocess.run(command, capture_output=True, timeout=600,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Trích xuất âm thanh quá lâu. Hãy chọn một đoạn mẫu ngắn hơn.") from exc
            if result.returncode:
                raise RuntimeError("Không đọc được âm thanh. Hãy chọn video có lời thoại hoặc tệp audio hợp lệ.")
            parts = sorted(Path(folder).glob("audio-*.mp3"))
            if not parts:
                raise RuntimeError("Video mẫu không có âm thanh để phân tích lời thoại.")
            texts = []
            for part in parts:
                if part.stat().st_size >= MAX_FILE_SIZE_MB * 1024 * 1024:
                    raise RuntimeError("Đoạn âm thanh còn quá lớn. Hãy chọn một đoạn mẫu ngắn hơn.")
                with part.open("rb") as stream:
                    transcript = self.client.audio.transcriptions.create(model="whisper-1", file=stream)
                text = (transcript.text or "").strip()
                if text:
                    texts.append(text)
            if not texts:
                raise RuntimeError("Không nhận diện được lời thoại nào trong file mẫu.")
            return "\n".join(texts)
