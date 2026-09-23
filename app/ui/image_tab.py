"""Tab 2: tạo ảnh minh họa bằng OpenAI."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.image_client import ImageClient
from app.core.grok_video_client import IMAGE_FILE_FILTER
from app.core.text_provider import PROVIDER_CLAUDE, get_text_client
from app.storage import history_store
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.ui.widgets.media_preview import MediaPreview
from app.ui.widgets.image_editor import ImageEditorDialog
from app.workers.async_worker import Worker
from app.ui.widgets.processing_dialog import ProcessingDialog


class ImageTab(QWidget):
    image_generated = Signal(Path)
    use_for_video = Signal(Path)
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._content_context = ""
        self._current_image_path: Path | None = None
        self._edit_versions = {}
        self._worker: Worker | None = None
        self._build_ui()
        self.processing_dialog = ProcessingDialog(self)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(make_page_header("🖼️ Tạo Ảnh", "Tạo ảnh minh họa cho bài đăng bằng OpenAI."))

        layout.addWidget(QLabel("Prompt mô tả ảnh (tiếng Anh cho kết quả tốt nhất):"))
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText(
            "VD: A Vietnamese farmer smiling while holding healthy green rice seedlings, "
            "golden hour lighting, photorealistic"
        )
        self.prompt_input.setFixedHeight(160)
        layout.addWidget(self.prompt_input)

        self.suggest_btn = QPushButton("Gợi ý prompt từ content")
        self.suggest_btn.setObjectName("linkButton")
        self.suggest_btn.setEnabled(False)
        self.suggest_btn.clicked.connect(self._on_suggest)
        layout.addWidget(self.suggest_btn)

        row = QHBoxLayout()
        row.addWidget(QLabel("Kích thước:"))
        self.size_combo = QComboBox()
        self.size_combo.addItems(["1024x1024", "1024x1536", "1536x1024"])
        row.addWidget(self.size_combo)
        layout.addLayout(row)

        self.generate_btn = QPushButton("Tạo ảnh với OpenAI")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.clicked.connect(self._on_generate)
        layout.addWidget(self.generate_btn)

        self.preview_label = MediaPreview("Chưa có ảnh")
        self.preview_label.setObjectName("mediaPreview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(240)
        layout.addWidget(self.preview_label)

        self.to_post_btn = QPushButton("→ Dùng cho tab Đăng Facebook")
        self.to_post_btn.setObjectName("linkButton")
        self.to_post_btn.setEnabled(False)
        self.to_post_btn.clicked.connect(self._on_use_for_post)
        layout.addWidget(self.to_post_btn)

        self.to_video_btn = QPushButton("→ Dùng làm vật liệu cho tab Tạo Video")
        self.to_video_btn.setObjectName("linkButton")
        self.to_video_btn.setEnabled(False)
        self.to_video_btn.clicked.connect(self._on_use_for_video)
        layout.addWidget(self.to_video_btn)
        self.edit_image_btn = QPushButton("Chỉnh sửa ảnh / Chọn vùng")
        self.edit_image_btn.setObjectName("primaryButton")
        self.edit_image_btn.clicked.connect(self._on_edit_image)
        layout.addWidget(self.edit_image_btn)
        self.open_edit_image_btn = QPushButton("Mở ảnh khác để chỉnh sửa")
        self.open_edit_image_btn.setObjectName("linkButton")
        self.open_edit_image_btn.clicked.connect(lambda: self._on_edit_image(choose_file=True))
        layout.addWidget(self.open_edit_image_btn)
        arrange_cards(layout, [("Thiết lập hình ảnh", [0, 1, 2, 3, 4]), ("Xem trước", [5, 8, 9, 6, 7])])

    def _on_edit_image(self, checked=False, *, choose_file=False) -> None:
        if self._worker and self._worker.isRunning():
            self.log_message.emit("Chờ tác vụ ảnh hiện tại hoàn tất trước khi chỉnh sửa.", "info")
            return
        path = self._current_image_path
        if choose_file or path is None:
            filename, _ = QFileDialog.getOpenFileName(self, "Mở ảnh để chỉnh sửa", "", IMAGE_FILE_FILTER)
            if not filename:
                return
            path = Path(filename)
        if QPixmap(str(path)).isNull():
            self.log_message.emit("Không đọc được ảnh đã chọn.", "error")
            return
        dialog = ImageEditorDialog(path, self._edit_versions.get(path), parent=self)
        dialog.use_btn.setText("Dùng ảnh này")
        result = dialog.exec()
        for version_path, _ in dialog.versions:
            self._edit_versions[version_path] = dialog.versions
        if result == QDialog.DialogCode.Accepted:
            self._current_image_path = dialog.current_path
            self.preview_label.setPixmap(QPixmap(str(dialog.current_path)))
            self.to_post_btn.setEnabled(True)
            self.to_video_btn.setEnabled(True)
            self.image_generated.emit(dialog.current_path)
        dialog.deleteLater()

    def set_context_from_content(self, content_text: str) -> None:
        self._content_context = content_text
        self.suggest_btn.setEnabled(bool(content_text.strip()))
        self.log_message.emit("Đã nhận content, có thể bấm 'Gợi ý prompt từ content'.", "info")

    def _on_suggest(self) -> None:
        provider = config.load_settings().get("content_provider", PROVIDER_CLAUDE)
        try:
            client = get_text_client(provider)
        except ValueError as exc:
            self.log_message.emit(str(exc), "error")
            return
        self.suggest_btn.setEnabled(False)
        self.log_message.emit("Đang nhờ AI gợi ý prompt ảnh...", "info")
        self._worker = Worker(client.suggest_image_prompt, content_text=self._content_context)
        self._worker.finished.connect(self._on_suggest_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_suggest_done(self, prompt: str) -> None:
        self.prompt_input.setPlainText(prompt)
        self.suggest_btn.setEnabled(True)
        self.log_message.emit("Đã có gợi ý prompt ảnh.", "success")

    def _on_generate(self) -> None:
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            self.log_message.emit("Vui lòng nhập prompt tạo ảnh.", "error")
            return
        try:
            settings = config.load_settings()
            client = ImageClient(config.get_secret("openai_api_key"), settings["openai_image_model"])
        except ValueError as exc:
            self.log_message.emit(str(exc), "error")
            return

        self.generate_btn.setEnabled(False)
        self.log_message.emit("Đang tạo ảnh với OpenAI...", "info")
        self._worker = Worker(
            client.generate_image,
            prompt=prompt,
            size=self.size_combo.currentText(),
            dest_dir=config.output_dir("images"),
        )
        self._worker.finished.connect(lambda path: self._on_done(prompt, path))
        self._worker.error.connect(self._on_error)
        self.processing_dialog.track(self._worker, "Đang tạo ảnh với OpenAI...")
        self._worker.start()

    def _on_done(self, prompt: str, path: Path) -> None:
        self.generate_btn.setEnabled(True)
        self._current_image_path = path
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            self.preview_label.setPixmap(pixmap)
        else:
            self.preview_label.setText("Không thể xem trước ảnh này.")
        self.to_post_btn.setEnabled(True)
        self.to_video_btn.setEnabled(True)
        history_store.add_image(prompt, str(path))
        self.image_generated.emit(path)
        self.log_message.emit(f"Đã tạo ảnh: {path}", "success")

    def _on_use_for_post(self) -> None:
        if self._current_image_path:
            self.image_generated.emit(self._current_image_path)

    def _on_use_for_video(self) -> None:
        if self._current_image_path:
            self.use_for_video.emit(self._current_image_path)
            self.log_message.emit("Đã gửi ảnh sang tab Tạo Video để làm vật liệu.", "info")

    def _on_error(self, message: str) -> None:
        self.generate_btn.setEnabled(True)
        self.suggest_btn.setEnabled(True)
        self.log_message.emit(f"Lỗi tạo ảnh: {message}", "error")
