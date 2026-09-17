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
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.heygen_client import HeyGenClient
from app.core.text_provider import PROVIDER_CLAUDE, PROVIDER_LABELS, PROVIDER_OPENAI
from app.core.automation_publisher import PLATFORM_LABELS, selected_platforms
from app.core.tiktok_client import PRIVACY_LABELS as TIKTOK_PRIVACY
from app.core.youtube_client import CATEGORY_LABELS, PRIVACY_LABELS as YOUTUBE_PRIVACY
from app.ui.widgets.row_list import RowListWidget
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
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
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

        self.auto_post_check = QCheckBox("Tự động đăng sau khi tạo xong")
        form.addRow("", self.auto_post_check)
        auto_post_hint = QLabel(
            "Khi bật, quy trình đăng lên các nền tảng và Page đã lưu bên dưới. "
            "Khi tắt, nội dung dừng lại để bạn duyệt. TikTok và YouTube cần video."
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

        publishing = QWidget()
        publishing_layout = QVBoxLayout(publishing)
        publishing_layout.setContentsMargins(0, 0, 0, 0)
        publishing_layout.setSpacing(12)
        publishing_layout.addWidget(QLabel("Nền tảng đăng bài"))
        self.platform_checks = {}
        for key, label in PLATFORM_LABELS.items():
            check = QCheckBox(label)
            self.platform_checks[key] = check
            publishing_layout.addWidget(check)
        publishing_layout.addWidget(QLabel("Page Facebook cho quy trình"))
        self.page_list = RowListWidget(height=140)
        self.page_checks = {}
        publishing_layout.addWidget(self.page_list)
        self.refresh_pages_btn = QPushButton("Cập nhật danh sách Page")
        self.refresh_pages_btn.clicked.connect(self._refresh_pages)
        publishing_layout.addWidget(self.refresh_pages_btn)
        publish_form = QFormLayout()
        publish_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.tiktok_privacy_combo = QComboBox()
        for key, label in TIKTOK_PRIVACY.items():
            self.tiktok_privacy_combo.addItem(label, key)
        publish_form.addRow("Quyền riêng tư TikTok:", self.tiktok_privacy_combo)
        self.tiktok_disable_comment = QCheckBox("Tắt bình luận TikTok")
        self.tiktok_disable_duet = QCheckBox("Tắt Duet TikTok")
        self.tiktok_disable_stitch = QCheckBox("Tắt Stitch TikTok")
        for check in (self.tiktok_disable_comment, self.tiktok_disable_duet, self.tiktok_disable_stitch):
            publish_form.addRow(check)
        self.youtube_privacy_combo = QComboBox()
        for key, label in YOUTUBE_PRIVACY.items():
            self.youtube_privacy_combo.addItem(label, key)
        publish_form.addRow("Quyền riêng tư YouTube:", self.youtube_privacy_combo)
        self.youtube_category_combo = QComboBox()
        for key, label in CATEGORY_LABELS.items():
            self.youtube_category_combo.addItem(label, key)
        publish_form.addRow("Chuyên mục YouTube:", self.youtube_category_combo)
        self.youtube_title_input = QLineEdit()
        self.youtube_title_input.setMaxLength(100)
        self.youtube_title_input.setPlaceholderText("Để trống: dùng ý tưởng của lần chạy")
        publish_form.addRow("Tiêu đề YouTube:", self.youtube_title_input)
        self.youtube_tags_input = QLineEdit()
        self.youtube_tags_input.setPlaceholderText("Các từ khóa cách nhau bằng dấu phẩy")
        publish_form.addRow("Từ khóa YouTube:", self.youtube_tags_input)
        publishing_layout.addLayout(publish_form)
        layout.addWidget(publishing)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.save_btn = QPushButton("Lưu cấu hình quy trình")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)
        arrange_cards(layout, [("Cấu hình mặc định", [0, 4, 5]), ("Xuất bản đa nền tảng", [3]), ("Avatar & giọng nói", [1, 2])])

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
        for key, check in self.platform_checks.items():
            check.setChecked(key in selected_platforms(settings))
        self._refresh_pages()
        for combo, key, default in (
            (self.tiktok_privacy_combo, "automation_tiktok_privacy", "SELF_ONLY"),
            (self.youtube_privacy_combo, "automation_youtube_privacy", "private"),
            (self.youtube_category_combo, "automation_youtube_category", "22"),
        ):
            index = combo.findData(settings.get(key, default))
            combo.setCurrentIndex(index if index >= 0 else combo.findData(default))
        for check, key in ((self.tiktok_disable_comment, "automation_tiktok_disable_comment"),
                           (self.tiktok_disable_duet, "automation_tiktok_disable_duet"),
                           (self.tiktok_disable_stitch, "automation_tiktok_disable_stitch")):
            check.setChecked(bool(settings.get(key, False)))
        self.youtube_title_input.setText(settings.get("automation_youtube_title", ""))
        self.youtube_tags_input.setText(settings.get("automation_youtube_tags", ""))

        # Pre-fill avatar/voice combos with just the saved id as a placeholder entry until
        # the user bấm "Tải danh sách" to fetch real display names.
        avatar_id = settings.get("heygen_avatar_id", "")
        if avatar_id:
            self.avatar_combo.addItem(avatar_id, avatar_id)
        voice_id = settings.get("heygen_voice_id", "")
        if voice_id:
            self.voice_combo.addItem(voice_id, voice_id)

    def _refresh_pages(self) -> None:
        selected = {key for key, check in self.page_checks.items() if check.isChecked()} if self.page_checks else set(config.load_settings().get("automation_facebook_page_ids", []))
        self.page_list.clear()
        self.page_checks = {}
        for page in config.list_pages():
            check = QCheckBox(page.get("name") or page["id"])
            check.setToolTip(f"ID: {page['id']}")
            check.setChecked(page["id"] in selected)
            self.page_checks[page["id"]] = check
            self.page_list.add_row(check)
        if not self.page_checks:
            hint = QLabel("Kết nối Facebook rồi cập nhật danh sách Page.")
            hint.setWordWrap(True)
            self.page_list.add_row(hint)

    def _on_save(self) -> None:
        platforms = [key for key, check in self.platform_checks.items() if check.isChecked()]
        if not platforms:
            self._notify("Chọn ít nhất một nền tảng đăng bài.", "error")
            return
        if any(key in platforms for key in ("tiktok", "youtube")) and self.attachment_combo.currentData() != ATTACHMENT_VIDEO:
            self._notify("Chọn đính kèm Video để đăng TikTok hoặc YouTube.", "error")
            return
        settings = config.load_settings()
        settings["content_provider"] = self.provider_combo.currentData()
        settings["automation_tone"] = self.tone_combo.currentText().strip() or "thân thiện, chuyên nghiệp"
        settings["automation_hashtags"] = self.hashtag_check.isChecked()
        settings["automation_attachment"] = self.attachment_combo.currentData()
        settings["automation_auto_post"] = self.auto_post_check.isChecked()
        settings["automation_platforms"] = platforms
        settings["automation_facebook_page_ids"] = [key for key, check in self.page_checks.items() if check.isChecked()]
        settings["automation_tiktok_privacy"] = self.tiktok_privacy_combo.currentData()
        settings["automation_youtube_privacy"] = self.youtube_privacy_combo.currentData()
        settings["automation_youtube_category"] = self.youtube_category_combo.currentData()
        settings["automation_youtube_title"] = self.youtube_title_input.text().strip()
        settings["automation_youtube_tags"] = self.youtube_tags_input.text().strip()
        for check, key in ((self.tiktok_disable_comment, "automation_tiktok_disable_comment"),
                           (self.tiktok_disable_duet, "automation_tiktok_disable_duet"),
                           (self.tiktok_disable_stitch, "automation_tiktok_disable_stitch")):
            settings[key] = check.isChecked()
        if self.avatar_combo.currentData():
            settings["heygen_avatar_id"] = self.avatar_combo.currentData()
        if self.voice_combo.currentData():
            settings["heygen_voice_id"] = self.voice_combo.currentData()
        config.save_settings(settings)

        self._notify("Cấu hình quy trình đã được lưu.", "success")

    def _notify(self, message: str, level: str) -> None:
        self.status_label.clear()
        self.log_message.emit(message, level)
