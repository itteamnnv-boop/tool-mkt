"""Dialog: preferences for the automated pipeline (provider, tone, attachment type,
default avatar/voice) — separate from the main app Settings and from the per-run idea
input, so the Automation screen itself can stay focused on running the pipeline."""
from __future__ import annotations

from PySide6.QtCore import Signal

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.heygen_client import HeyGenClient
from app.core.text_provider import PROVIDER_CLAUDE, PROVIDER_LABELS, PROVIDER_OPENAI
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.workers.async_worker import Worker

ATTACHMENT_NONE = "none"
ATTACHMENT_IMAGE = "image"
ATTACHMENT_VIDEO = "video"

_ATTACHMENT_LABELS = {
    ATTACHMENT_NONE: "Không đính kèm (chỉ text)",
    ATTACHMENT_IMAGE: "Ảnh (OpenAI)",
    ATTACHMENT_VIDEO: "Video (HeyGen)",
}


class AutomationSettingsTab(QWidget):
    log_message = Signal(str, str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Worker | None = None
        self._build_ui()
        self._load_current_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            make_page_header(
                "⚙️ Cài đặt quy trình tự động",
                "Các mặc định dùng mỗi lần chạy quy trình — không cần chọn lại mỗi khi nhập ý tưởng mới.",
            )
        )

        form = QFormLayout()
        form.setVerticalSpacing(8)

        self.provider_combo = QComboBox()
        self.provider_combo.addItem(PROVIDER_LABELS[PROVIDER_CLAUDE], PROVIDER_CLAUDE)
        self.provider_combo.addItem(PROVIDER_LABELS[PROVIDER_OPENAI], PROVIDER_OPENAI)
        form.addRow("Nhà cung cấp viết content:", self.provider_combo)

        self.tone_combo = QComboBox()
        self.tone_combo.addItems(
            ["thân thiện, chuyên nghiệp", "hài hước, gần gũi", "trang trọng", "thúc đẩy hành động (khuyến mãi)"]
        )
        self.tone_combo.setEditable(True)
        form.addRow("Giọng điệu:", self.tone_combo)

        self.hashtag_check = QCheckBox("Thêm hashtag")
        form.addRow("", self.hashtag_check)

        self.attachment_combo = QComboBox()
        for key in (ATTACHMENT_NONE, ATTACHMENT_IMAGE, ATTACHMENT_VIDEO):
            self.attachment_combo.addItem(_ATTACHMENT_LABELS[key], key)
        self.attachment_combo.currentIndexChanged.connect(self._on_attachment_changed)
        form.addRow("Đính kèm khi đăng:", self.attachment_combo)

        self.auto_post_check = QCheckBox("Tự động đăng ngay sau khi tạo xong (không cần chờ duyệt)")
        form.addRow("", self.auto_post_check)
        auto_post_hint = QLabel(
            "⚠ Khi bật: sau khi viết content và tạo ảnh/video xong, app tự đăng luôn lên các Page đang "
            "chọn — không dừng lại để bạn xem trước hay xác nhận. Chỉ bật khi bạn tin tưởng nội dung AI "
            "tạo ra và đã chọn đúng Page ở tab Đăng Facebook."
        )
        auto_post_hint.setWordWrap(True)
        auto_post_hint.setObjectName("mutedHint")
        form.addRow("", auto_post_hint)

        layout.addLayout(form)

        self.video_options_label = QLabel("Avatar/Voice mặc định cho Video:")
        layout.addWidget(self.video_options_label)
        video_row = QFormLayout()
        self.load_avatars_btn = QPushButton("Tải danh sách")
        self.load_avatars_btn.setObjectName("linkButton")
        self.load_avatars_btn.clicked.connect(self._on_load_avatars)
        video_row.addRow(self.load_avatars_btn)
        self.avatar_combo = QComboBox()
        video_row.addRow("Avatar:", self.avatar_combo)
        self.voice_combo = QComboBox()
        video_row.addRow("Voice:", self.voice_combo)
        layout.addLayout(video_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.save_btn = QPushButton("Lưu cấu hình quy trình")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)
        arrange_cards(layout, [("Cấu hình mặc định", [0, 3, 4]), ("Avatar & giọng nói", [1, 2])])

        self._on_attachment_changed()

    def _on_attachment_changed(self) -> None:
        is_video = self.attachment_combo.currentData() == ATTACHMENT_VIDEO
        self.video_options_label.setText(
            "Avatar/Voice mặc định cho Video:" if is_video
            else "Chọn loại đính kèm Video để thiết lập avatar và giọng nói."
        )
        self.load_avatars_btn.setEnabled(is_video)
        self.avatar_combo.setEnabled(is_video)
        self.voice_combo.setEnabled(is_video)

    def _on_load_avatars(self) -> None:
        try:
            client = HeyGenClient(config.get_secret("heygen_api_key"))
        except ValueError as exc:
            self._notify(str(exc), "error")
            return
        self.load_avatars_btn.setEnabled(False)
        self._notify("Đang tải danh sách avatar/voice...", "info")
        self._worker = Worker(self._fetch_avatars_and_voices, client)
        self._worker.finished.connect(self._on_avatars_loaded)
        self._worker.error.connect(self._on_load_error)
        self._worker.start()

    @staticmethod
    def _fetch_avatars_and_voices(client: HeyGenClient) -> tuple[list[dict], list[dict]]:
        return client.list_avatars(), client.list_voices()

    def _on_avatars_loaded(self, result: tuple[list[dict], list[dict]]) -> None:
        avatars, voices = result
        settings = config.load_settings()

        self.avatar_combo.clear()
        for a in avatars:
            self.avatar_combo.addItem(a.get("avatar_name", a.get("avatar_id", "?")), a.get("avatar_id"))
        idx = self.avatar_combo.findData(settings.get("heygen_avatar_id", ""))
        if idx >= 0:
            self.avatar_combo.setCurrentIndex(idx)

        self.voice_combo.clear()
        for v in voices:
            label = f"{v.get('name', v.get('voice_id', '?'))} ({v.get('language', '')})"
            self.voice_combo.addItem(label, v.get("voice_id"))
        idx = self.voice_combo.findData(settings.get("heygen_voice_id", ""))
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)

        self.load_avatars_btn.setEnabled(True)
        self._notify(f"Đã tải {len(avatars)} avatar và {len(voices)} voice.", "success")

    def _on_load_error(self, message: str) -> None:
        self.load_avatars_btn.setEnabled(True)
        self._notify(f"Lỗi tải avatar/voice: {message}", "error")

    def _load_current_values(self) -> None:
        settings = config.load_settings()

        idx = self.provider_combo.findData(settings.get("content_provider", PROVIDER_CLAUDE))
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)

        self.tone_combo.setCurrentText(settings.get("automation_tone", "thân thiện, chuyên nghiệp"))
        self.hashtag_check.setChecked(bool(settings.get("automation_hashtags", True)))

        idx = self.attachment_combo.findData(settings.get("automation_attachment", ATTACHMENT_IMAGE))
        if idx >= 0:
            self.attachment_combo.setCurrentIndex(idx)

        self.auto_post_check.setChecked(bool(settings.get("automation_auto_post", False)))

        # Pre-fill avatar/voice combos with just the saved id as a placeholder entry until
        # the user bấm "Tải danh sách" to fetch real display names.
        avatar_id = settings.get("heygen_avatar_id", "")
        if avatar_id:
            self.avatar_combo.addItem(avatar_id, avatar_id)
        voice_id = settings.get("heygen_voice_id", "")
        if voice_id:
            self.voice_combo.addItem(voice_id, voice_id)

    def _on_save(self) -> None:
        settings = config.load_settings()
        settings["content_provider"] = self.provider_combo.currentData()
        settings["automation_tone"] = self.tone_combo.currentText().strip() or "thân thiện, chuyên nghiệp"
        settings["automation_hashtags"] = self.hashtag_check.isChecked()
        settings["automation_attachment"] = self.attachment_combo.currentData()
        settings["automation_auto_post"] = self.auto_post_check.isChecked()
        if self.avatar_combo.currentData():
            settings["heygen_avatar_id"] = self.avatar_combo.currentData()
        if self.voice_combo.currentData():
            settings["heygen_voice_id"] = self.voice_combo.currentData()
        config.save_settings(settings)

        self._notify("Cấu hình quy trình đã được lưu.", "success")

    def _notify(self, message: str, level: str) -> None:
        self.status_label.clear()
        self.log_message.emit(message, level)
