"""Tab 3: tạo video avatar nói bằng HeyGen, hoặc video từ mô tả bằng Grok (xAI)."""
from __future__ import annotations

import os
import threading
from pathlib import Path

import requests
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.heygen_client import HeyGenClient
from app.core.grok_video_client import (
    ASPECT_RATIOS,
    IMAGE_FILE_FILTER,
    MAX_REFERENCE_IMAGES,
    RESOLUTIONS,
    GrokVideoClient,
)
from app.core.transcription_client import SAMPLE_FILE_FILTER, TranscriptionClient
from app.core.text_provider import PROVIDER_CLAUDE, get_text_client
from app.storage import history_store
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.ui.widgets.media_preview import MediaPreview
from app.workers.async_worker import Worker

PROVIDER_HEYGEN = "heygen"
PROVIDER_GROK = "grok"


class VideoTab(QWidget):
    video_generated = Signal(Path)
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._content_context = ""
        self._current_video_path: Path | None = None
        self._reference_image_path: Path | None = None
        self._material_image_paths: list[Path] = []
        self._avatar_previews: dict[str, str] = {}
        self._worker: Worker | None = None
        self._preview_worker: Worker | None = None
        self._cancel_event: threading.Event | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(make_page_header("🎬 Tạo Video", "Tạo video avatar nói bằng HeyGen, hoặc video từ mô tả bằng Grok (xAI)."))

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Nhà cung cấp:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("HeyGen (Avatar nói kịch bản)", PROVIDER_HEYGEN)
        self.provider_combo.addItem("Grok (xAI - tạo video từ mô tả)", PROVIDER_GROK)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_row.addWidget(self.provider_combo, 1)
        layout.addLayout(provider_row)

        self.load_avatars_btn = QPushButton("Tải danh sách Avatar / Voice từ HeyGen")
        self.load_avatars_btn.setObjectName("linkButton")
        self.load_avatars_btn.clicked.connect(self._on_load_avatars)
        layout.addWidget(self.load_avatars_btn)

        self.heygen_options = QWidget()
        row = QHBoxLayout(self.heygen_options)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Avatar:"))
        self.avatar_combo = QComboBox()
        self.avatar_combo.currentIndexChanged.connect(self._on_avatar_selected)
        row.addWidget(self.avatar_combo)
        row.addWidget(QLabel("Voice:"))
        self.voice_combo = QComboBox()
        row.addWidget(self.voice_combo)
        layout.addWidget(self.heygen_options)

        self.grok_options = QWidget()
        grok_options_layout = QVBoxLayout(self.grok_options)
        grok_options_layout.setContentsMargins(0, 0, 0, 0)
        grok_options_layout.setSpacing(6)

        grok_row = QHBoxLayout()
        grok_row.addWidget(QLabel("Tỉ lệ:"))
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(ASPECT_RATIOS)
        grok_row.addWidget(self.aspect_combo)
        grok_row.addWidget(QLabel("Độ phân giải:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(RESOLUTIONS)
        grok_row.addWidget(self.resolution_combo)
        grok_row.addWidget(QLabel("Thời lượng (giây):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 15)
        self.duration_spin.setValue(6)
        grok_row.addWidget(self.duration_spin)
        grok_options_layout.addLayout(grok_row)

        image_row = QHBoxLayout()
        self.attach_image_btn = QPushButton("📎 Ảnh khởi đầu video (ghim khung hình đầu)")
        self.attach_image_btn.setObjectName("linkButton")
        self.attach_image_btn.clicked.connect(self._on_attach_image)
        image_row.addWidget(self.attach_image_btn)
        self.reference_thumb = QLabel()
        self.reference_thumb.setFixedSize(48, 48)
        self.reference_thumb.setScaledContents(True)
        self.reference_thumb.setVisible(False)
        image_row.addWidget(self.reference_thumb)
        self.reference_image_label = QLabel("Không có ảnh khởi đầu — Grok sẽ tự tạo khung hình đầu từ mô tả.")
        self.reference_image_label.setObjectName("mutedHint")
        image_row.addWidget(self.reference_image_label, 1)
        self.clear_image_btn = QPushButton("✕ Bỏ ảnh")
        self.clear_image_btn.setObjectName("linkButton")
        self.clear_image_btn.setEnabled(False)
        self.clear_image_btn.clicked.connect(self._on_clear_reference_image)
        image_row.addWidget(self.clear_image_btn)
        grok_options_layout.addLayout(image_row)

        materials_header_row = QHBoxLayout()
        self.add_material_btn = QPushButton("🧑 + Thêm ảnh vật liệu tham chiếu (khuôn mặt, phong cách...)")
        self.add_material_btn.setObjectName("linkButton")
        self.add_material_btn.clicked.connect(self._on_add_materials)
        materials_header_row.addWidget(self.add_material_btn)
        self.materials_hint_label = QLabel("Chưa có ảnh vật liệu tham chiếu nào.")
        self.materials_hint_label.setObjectName("mutedHint")
        materials_header_row.addWidget(self.materials_hint_label, 1)
        grok_options_layout.addLayout(materials_header_row)

        self.materials_strip = QWidget()
        self.materials_strip_layout = QHBoxLayout(self.materials_strip)
        self.materials_strip_layout.setContentsMargins(0, 0, 0, 0)
        self.materials_strip_layout.setSpacing(8)
        self.materials_strip_layout.addStretch(1)
        grok_options_layout.addWidget(self.materials_strip)

        layout.addWidget(self.grok_options)

        self.script_label = QLabel("Kịch bản (script) để avatar đọc:")
        layout.addWidget(self.script_label)
        self.script_input = QTextEdit()
        self.script_input.setPlaceholderText("Nhập lời thoại cho video, hoặc dùng nút gợi ý bên dưới.")
        layout.addWidget(self.script_input)

        self.suggest_btn = QPushButton("Gợi ý kịch bản từ content")
        self.suggest_btn.setObjectName("linkButton")
        self.suggest_btn.setEnabled(False)
        self.suggest_btn.clicked.connect(self._on_suggest)
        layout.addWidget(self.suggest_btn)

        self.reference_video_btn = QPushButton("📎 Đính kèm video mẫu (lấy kịch bản/ý tưởng)")
        self.reference_video_btn.setObjectName("linkButton")
        self.reference_video_btn.clicked.connect(self._on_attach_reference_video)
        layout.addWidget(self.reference_video_btn)

        generate_row = QHBoxLayout()
        self.generate_btn = QPushButton("Tạo video với HeyGen")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.clicked.connect(self._on_generate)
        generate_row.addWidget(self.generate_btn, 1)
        self.stop_btn = QPushButton("⏹ Dừng tạo")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_generate)
        generate_row.addWidget(self.stop_btn)
        layout.addLayout(generate_row)

        self.preview = MediaPreview("Chưa có video. Chọn Avatar để xem trước.")
        self.preview.setMinimumHeight(200)
        layout.addWidget(self.preview)

        self.status_caption = QLabel("")
        self.status_caption.setObjectName("mutedHint")
        self.status_caption.setWordWrap(True)
        layout.addWidget(self.status_caption)

        actions = QVBoxLayout()
        self.open_btn = QPushButton("Mở video")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._on_open_video)
        self.to_post_btn = QPushButton("→ Dùng cho tab Đăng Facebook")
        self.to_post_btn.setObjectName("linkButton")
        self.to_post_btn.setEnabled(False)
        self.to_post_btn.clicked.connect(self._on_use_for_post)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.to_post_btn)
        layout.addLayout(actions)
        arrange_cards(layout, [("Kịch bản & avatar", list(range(9))), ("Video của bạn", [9, 10, 11])])

        self._load_provider_setting()
        self._on_provider_changed()

    def set_context_from_content(self, content_text: str) -> None:
        self._content_context = content_text
        self.suggest_btn.setEnabled(bool(content_text.strip()))
        self.log_message.emit("Đã nhận content, có thể bấm 'Gợi ý kịch bản từ content'.", "info")

    def _make_heygen_client(self) -> HeyGenClient | None:
        try:
            return HeyGenClient(config.get_secret("heygen_api_key"))
        except ValueError as exc:
            self.log_message.emit(str(exc), "error")
            return None

    def _make_grok_client(self) -> GrokVideoClient | None:
        try:
            return GrokVideoClient(config.get_secret("grok_api_key"))
        except ValueError as exc:
            self.log_message.emit(str(exc), "error")
            return None

    def _on_attach_image(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh vật liệu", "", IMAGE_FILE_FILTER)
        if path_str:
            self.set_reference_image(Path(path_str))

    def set_reference_image(self, path: Path) -> None:
        """Set the local image Grok will animate (image-to-video). Called either from the
        file picker or from ImageTab's "Dùng làm vật liệu cho tab Tạo Video" button."""
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.log_message.emit(f"Không đọc được ảnh: {path}", "error")
            return
        self._reference_image_path = path
        self.reference_thumb.setPixmap(pixmap)
        self.reference_thumb.setVisible(True)
        self.reference_image_label.setText(f"Vật liệu: {path.name}")
        self.clear_image_btn.setEnabled(True)
        self.log_message.emit(f"Đã đính kèm ảnh vật liệu cho Grok: {path.name}", "info")

    def _on_clear_reference_image(self) -> None:
        self._reference_image_path = None
        self.reference_thumb.clear()
        self.reference_thumb.setVisible(False)
        self.reference_image_label.setText("Không có ảnh khởi đầu — Grok sẽ tự tạo khung hình đầu từ mô tả.")
        self.clear_image_btn.setEnabled(False)

    def _on_add_materials(self) -> None:
        paths_str, _ = QFileDialog.getOpenFileNames(self, "Chọn ảnh vật liệu tham chiếu", "", IMAGE_FILE_FILTER)
        if not paths_str:
            return
        room_left = MAX_REFERENCE_IMAGES - len(self._material_image_paths)
        if room_left <= 0:
            self.log_message.emit(f"Đã đạt giới hạn {MAX_REFERENCE_IMAGES} ảnh vật liệu tham chiếu.", "error")
            return
        added = 0
        for path_str in paths_str:
            if added >= room_left:
                break
            pixmap = QPixmap(path_str)
            if pixmap.isNull():
                self.log_message.emit(f"Không đọc được ảnh: {path_str}", "error")
                continue
            self._material_image_paths.append(Path(path_str))
            added += 1
        if len(paths_str) > added:
            self.log_message.emit(
                f"Chỉ thêm được {added} ảnh — tối đa {MAX_REFERENCE_IMAGES} ảnh vật liệu tham chiếu.", "info"
            )
        self._refresh_materials_strip()

    def _remove_material(self, path: Path) -> None:
        if path in self._material_image_paths:
            self._material_image_paths.remove(path)
        self._refresh_materials_strip()

    def _refresh_materials_strip(self) -> None:
        while self.materials_strip_layout.count() > 1:  # keep the trailing stretch at the end
            item = self.materials_strip_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for path in self._material_image_paths:
            thumb_widget = QWidget()
            thumb_layout = QVBoxLayout(thumb_widget)
            thumb_layout.setContentsMargins(0, 0, 0, 0)
            thumb_layout.setSpacing(2)
            thumb_label = QLabel()
            thumb_label.setFixedSize(48, 48)
            thumb_label.setScaledContents(True)
            thumb_label.setPixmap(QPixmap(str(path)))
            thumb_label.setToolTip(path.name)
            thumb_layout.addWidget(thumb_label)
            remove_btn = QPushButton("✕")
            remove_btn.setFixedWidth(48)
            remove_btn.clicked.connect(lambda _checked=False, p=path: self._remove_material(p))
            thumb_layout.addWidget(remove_btn)
            self.materials_strip_layout.insertWidget(self.materials_strip_layout.count() - 1, thumb_widget)

        count = len(self._material_image_paths)
        if count == 0:
            self.materials_hint_label.setText("Chưa có ảnh vật liệu tham chiếu nào.")
        else:
            self.materials_hint_label.setText(
                f"Đã chọn {count}/{MAX_REFERENCE_IMAGES} ảnh vật liệu tham chiếu (khuôn mặt, phong cách...)."
            )

    def _load_provider_setting(self) -> None:
        settings = config.load_settings()
        provider = settings.get("video_provider", PROVIDER_HEYGEN)
        idx = self.provider_combo.findData(provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        idx = self.aspect_combo.findText(settings.get("grok_aspect_ratio", "16:9"))
        if idx >= 0:
            self.aspect_combo.setCurrentIndex(idx)
        idx = self.resolution_combo.findText(settings.get("grok_resolution", "720p"))
        if idx >= 0:
            self.resolution_combo.setCurrentIndex(idx)
        self.duration_spin.setValue(int(settings.get("grok_duration", 6)))

    def _current_provider(self) -> str:
        return self.provider_combo.currentData() or PROVIDER_HEYGEN

    def _on_provider_changed(self) -> None:
        provider = self._current_provider()
        is_heygen = provider == PROVIDER_HEYGEN

        self.load_avatars_btn.setVisible(is_heygen)
        self.heygen_options.setVisible(is_heygen)
        self.grok_options.setVisible(not is_heygen)

        if is_heygen:
            self.script_label.setText("Kịch bản (script) để avatar đọc:")
            self.script_input.setPlaceholderText("Nhập lời thoại cho video, hoặc dùng nút gợi ý bên dưới.")
            self.generate_btn.setText("Tạo video với HeyGen")
            if not self._avatar_previews:
                self.preview.setText("Chưa có video. Chọn Avatar để xem trước.")
        else:
            self.script_label.setText("Mô tả video (prompt) cho Grok:")
            self.script_input.setPlaceholderText(
                "Mô tả cảnh quay bạn muốn Grok tạo, hoặc dùng nút gợi ý bên dưới."
            )
            self.generate_btn.setText("Tạo video với Grok")
            self.preview.setText("Chưa có video. Nhập mô tả và bấm Tạo video.")

        settings = config.load_settings()
        settings["video_provider"] = provider
        config.save_settings(settings)

    def _on_load_avatars(self) -> None:
        client = self._make_heygen_client()
        if not client:
            return
        self.load_avatars_btn.setEnabled(False)
        self.log_message.emit("Đang tải danh sách avatar/voice từ HeyGen...", "info")
        self._worker = Worker(self._fetch_avatars_and_voices, client)
        self._worker.finished.connect(self._on_avatars_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @staticmethod
    def _fetch_avatars_and_voices(client: HeyGenClient) -> tuple[list[dict], list[dict]]:
        return client.list_avatars(), client.list_voices()

    def _on_avatars_loaded(self, result: tuple[list[dict], list[dict]]) -> None:
        avatars, voices = result
        self.avatar_combo.clear()
        self._avatar_previews.clear()
        for a in avatars:
            avatar_id = a.get("avatar_id")
            self.avatar_combo.addItem(a.get("avatar_name", avatar_id or "?"), avatar_id)
            preview_url = a.get("preview_image_url") or a.get("preview_image") or a.get("image_url")
            if avatar_id and preview_url:
                self._avatar_previews[avatar_id] = preview_url
        self.voice_combo.clear()
        for v in voices:
            label = f"{v.get('name', v.get('voice_id', '?'))} ({v.get('language', '')})"
            self.voice_combo.addItem(label, v.get("voice_id"))
        self.load_avatars_btn.setEnabled(True)
        self.log_message.emit(f"Đã tải {len(avatars)} avatar và {len(voices)} voice.", "success")

    def _on_avatar_selected(self) -> None:
        avatar_id = self.avatar_combo.currentData()
        url = self._avatar_previews.get(avatar_id, "") if avatar_id else ""
        if url:
            self._load_preview_image(url, caption=f"Avatar: {self.avatar_combo.currentText()}")
        else:
            self.preview.setText("Chưa có video. Chọn Avatar để xem trước.")
            self.status_caption.setText("")

    def _load_preview_image(self, url: str, caption: str) -> None:
        self._preview_worker = Worker(self._fetch_image_bytes, url)
        self._preview_worker.finished.connect(lambda data: self._on_preview_image_loaded(data, caption))
        self._preview_worker.error.connect(lambda _msg: None)  # a missing preview image is not worth alarming over
        self._preview_worker.start()

    @staticmethod
    def _fetch_image_bytes(url: str) -> bytes:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.content

    def _on_preview_image_loaded(self, data: bytes, caption: str) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.preview.setPixmap(pixmap)
            self.status_caption.setText(caption)

    def _on_suggest(self) -> None:
        provider = config.load_settings().get("content_provider", PROVIDER_CLAUDE)
        try:
            client = get_text_client(provider)
        except ValueError as exc:
            self.log_message.emit(str(exc), "error")
            return
        self.suggest_btn.setEnabled(False)
        self.log_message.emit("Đang nhờ AI gợi ý kịch bản video...", "info")
        self._worker = Worker(client.suggest_video_script, content_text=self._content_context)
        self._worker.finished.connect(self._on_suggest_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_suggest_done(self, script: str) -> None:
        self.script_input.setPlainText(script)
        self.suggest_btn.setEnabled(True)
        self.log_message.emit("Đã có gợi ý kịch bản.", "success")

    def _on_attach_reference_video(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Chọn video/audio mẫu", "", SAMPLE_FILE_FILTER)
        if not path_str:
            return
        try:
            transcription_client = TranscriptionClient(config.get_secret("openai_api_key"))
        except ValueError as exc:
            self.log_message.emit(str(exc), "error")
            return
        provider = config.load_settings().get("content_provider", PROVIDER_CLAUDE)
        try:
            text_client = get_text_client(provider)
        except ValueError as exc:
            self.log_message.emit(str(exc), "error")
            return

        self.reference_video_btn.setEnabled(False)
        self.suggest_btn.setEnabled(False)
        self.log_message.emit("Đang trích xuất lời thoại từ video mẫu...", "info")
        self._worker = Worker(
            self._build_script_from_reference,
            transcription_client=transcription_client,
            text_client=text_client,
            file_path=Path(path_str),
            content_text=self._content_context,
        )
        self._worker.progress.connect(lambda msg: self.log_message.emit(msg, "info"))
        self._worker.finished.connect(self._on_reference_script_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @staticmethod
    def _build_script_from_reference(
        transcription_client: TranscriptionClient,
        text_client,
        file_path: Path,
        content_text: str,
        on_progress=None,
    ) -> str:
        transcript = transcription_client.transcribe(file_path)
        if on_progress:
            on_progress("Đã có lời thoại video mẫu, đang viết kịch bản mới lấy cảm hứng...")
        return text_client.suggest_video_script_from_reference(transcript, content_text)

    def _on_reference_script_done(self, script: str) -> None:
        self.script_input.setPlainText(script)
        self.reference_video_btn.setEnabled(True)
        self.suggest_btn.setEnabled(bool(self._content_context.strip()))
        self.log_message.emit("Đã tạo kịch bản mới lấy cảm hứng từ video mẫu.", "success")

    def _on_generate(self) -> None:
        if self._current_provider() == PROVIDER_HEYGEN:
            self._on_generate_heygen()
        else:
            self._on_generate_grok()

    def _on_generate_heygen(self) -> None:
        script = self.script_input.toPlainText().strip()
        if not script:
            self.log_message.emit("Vui lòng nhập kịch bản.", "error")
            return
        avatar_id = self.avatar_combo.currentData()
        voice_id = self.voice_combo.currentData()
        if not avatar_id or not voice_id:
            self.log_message.emit("Vui lòng tải và chọn Avatar/Voice trước.", "error")
            return
        client = self._make_heygen_client()
        if not client:
            return

        self._start_generation("Đang tạo video với HeyGen, thao tác này có thể mất vài phút...")
        self._worker = Worker(
            client.generate_and_wait,
            avatar_id=avatar_id,
            voice_id=voice_id,
            script_text=script,
            dest_dir=config.output_dir("videos"),
            cancel_event=self._cancel_event,
        )
        self._worker.progress.connect(lambda msg: self.status_caption.setText(msg))
        self._worker.thumbnail.connect(self._on_thumbnail_ready)
        self._worker.finished.connect(lambda path: self._on_done(script, path))
        self._worker.error.connect(self._on_error)
        self._worker.cancelled.connect(self._on_generate_cancelled)
        self._worker.start()

    def _on_generate_grok(self) -> None:
        prompt = self.script_input.toPlainText().strip()
        if not prompt:
            self.log_message.emit("Vui lòng nhập mô tả video (prompt).", "error")
            return
        client = self._make_grok_client()
        if not client:
            return

        aspect_ratio = self.aspect_combo.currentText()
        resolution = self.resolution_combo.currentText()
        duration = self.duration_spin.value()
        settings = config.load_settings()
        settings["grok_aspect_ratio"] = aspect_ratio
        settings["grok_resolution"] = resolution
        settings["grok_duration"] = duration
        config.save_settings(settings)

        has_materials = self._reference_image_path or self._material_image_paths
        message = (
            "Đang tạo video với Grok từ ảnh vật liệu, thao tác này có thể mất vài phút..."
            if has_materials
            else "Đang tạo video với Grok, thao tác này có thể mất vài phút..."
        )
        self._start_generation(message)
        self._worker = Worker(
            client.generate_and_wait,
            prompt=prompt,
            dest_dir=config.output_dir("videos"),
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            image_path=self._reference_image_path,
            reference_image_paths=self._material_image_paths or None,
            cancel_event=self._cancel_event,
        )
        self._worker.progress.connect(lambda msg: self.status_caption.setText(msg))
        self._worker.finished.connect(lambda path: self._on_done(prompt, path))
        self._worker.error.connect(self._on_error)
        self._worker.cancelled.connect(self._on_generate_cancelled)
        self._worker.start()

    def _start_generation(self, message: str) -> None:
        self.generate_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.open_btn.setEnabled(False)
        self.to_post_btn.setEnabled(False)
        self.log_message.emit(message, "info")
        self.status_caption.setText("Đang xử lý...")
        self._cancel_event = threading.Event()

    def _on_stop_generate(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        self.stop_btn.setEnabled(False)
        self.status_caption.setText("Đang huỷ...")
        self.log_message.emit("Đang huỷ tạo video (chờ vòng kiểm tra kế tiếp)...", "info")

    def _on_generate_cancelled(self) -> None:
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._cancel_event = None
        self.status_caption.setText("Đã huỷ tạo video.")
        self.log_message.emit("Đã huỷ tạo video theo yêu cầu.", "info")

    def _on_thumbnail_ready(self, url: str) -> None:
        # A real frame from the video HeyGen is rendering — swap it in for the static
        # avatar photo so the preview tracks actual progress, not just a placeholder.
        self._load_preview_image(url, caption="Khung hình từ video đang tạo (HeyGen)")

    def _on_done(self, script: str, path: Path) -> None:
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._cancel_event = None
        self._current_video_path = path
        self.status_caption.setText(f"Hoàn tất: {path}")
        self.open_btn.setEnabled(True)
        self.to_post_btn.setEnabled(True)
        history_store.add_video(script, str(path))
        self.video_generated.emit(path)
        self.log_message.emit(f"Đã tạo video: {path}", "success")

    def _on_open_video(self) -> None:
        if self._current_video_path:
            os.startfile(self._current_video_path)  # noqa: S606 - user-initiated, local file only

    def _on_use_for_post(self) -> None:
        if self._current_video_path:
            self.video_generated.emit(self._current_video_path)

    def _on_error(self, message: str) -> None:
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._cancel_event = None
        self.load_avatars_btn.setEnabled(True)
        self.suggest_btn.setEnabled(True)
        self.reference_video_btn.setEnabled(True)
        self.status_caption.setText(f"Lỗi: {message}")
        self.log_message.emit(f"Lỗi tạo video: {message}", "error")
