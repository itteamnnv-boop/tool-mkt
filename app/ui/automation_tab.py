"""Fully automated pipeline, shown as a 3-step timeline: Content -> (optional) Image/Video
-> Review & Post. Preferences (provider, tone, attachment type, default avatar/voice) live
in their own settings dialog (⚙ button) so this screen stays focused on running the
pipeline and watching its progress rather than a long form of options."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from copy import deepcopy

import requests
from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.automation_publisher import configured_pages, selected_platforms, validate_destinations, PLATFORM_LABELS
from app.core.heygen_client import HeyGenClient
from app.core.image_client import ImageClient
from app.core.text_provider import PROVIDER_LABELS, get_text_client
from app.storage import history_store
from app.ui.automation_settings_dialog import (
    ATTACHMENT_IMAGE,
    ATTACHMENT_NONE,
    ATTACHMENT_VIDEO,
)
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import card
from app.ui.widgets.media_preview import MediaPreview
from app.ui.widgets.facebook_post_preview import FacebookPostPreview
from app.ui.widgets.pages_selector import PagesSelectorWidget
from app.ui.widgets.processing_dialog import ProcessingDialog
from app.ui.widgets.timeline import STATUS_ACTIVE, STATUS_DONE, STATUS_ERROR, STATUS_SKIPPED, TimelineWidget
from app.workers.async_worker import Worker


class AutomationTab(QWidget):
    log_message = Signal(str, str)
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Worker | None = None
        self._thumbnail_worker: Worker | None = None
        self._content_text = ""
        self._image_path: Path | None = None
        self._image_paths: list[Path] = []
        self._image_prompt = ""
        self._video_path: Path | None = None
        self._active_step = None
        self._run_settings = None
        self._run_pages = []
        self._run_topic = ""
        self._published_targets = set()
        self._build_ui()
        self.processing_dialog = ProcessingDialog(self)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        self.setObjectName("automationWorkspace")
        self.setStyleSheet("""
            QWidget#automationWorkspace QLabel, QWidget#automationWorkspace QCheckBox,
            QWidget#automationWorkspace QTextEdit, QWidget#automationWorkspace QDateTimeEdit { font-size: 12px; }
            QWidget#automationWorkspace QLabel#pageHeader { font-size: 23px; }
            QWidget#automationWorkspace QLabel#pageSubheader { font-size: 12px; }
            QWidget#automationWorkspace QLabel#cardTitle { font-size: 13px; padding: 10px 12px 4px 12px; }
            QWidget#automationWorkspace QLabel#timelineTitle { font-size: 12px; }
            QWidget#automationWorkspace QLabel#timelineStatus { font-size: 11px; }
            QWidget#automationWorkspace QPushButton { font-size: 12px; min-height: 0px; padding: 4px 10px; border-radius: 9px; }
            QWidget#automationWorkspace QTextEdit { padding: 7px; }
            QWidget#automationWorkspace QDateTimeEdit { padding: 4px 6px; }
            QWidget#automationWorkspace QTabBar::tab { font-size: 12px; padding: 5px 9px; min-height: 0px; }
            QScrollArea#automationControls { background: transparent; border: none; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.addWidget(
            make_page_header(
                "🚀 Quy trình tự động",
                "Nhập 1 ý tưởng — AI tự động viết content rồi tạo ảnh/video theo cấu hình đã lưu.",
            ),
            1,
        )
        self.settings_btn = QPushButton("Cài đặt quy trình")
        self.settings_btn.setObjectName("linkButton")
        self.settings_btn.clicked.connect(self._on_open_settings)
        header_row.addWidget(self.settings_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        layout.addLayout(columns, 1)
        self.controls_scroll = QScrollArea()
        self.controls_scroll.setObjectName("automationControls")
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setMinimumWidth(320)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls = QWidget()
        setup = QVBoxLayout(controls)
        setup.setContentsMargins(0, 0, 4, 0)
        setup.setSpacing(10)
        self.controls_scroll.setWidget(controls)
        columns.addWidget(self.controls_scroll, 2)
        workspace = QVBoxLayout()
        workspace.setSpacing(10)
        columns.addLayout(workspace, 3)

        idea_card, idea_layout = card("1. Ý tưởng & cấu hình")
        idea_layout.setContentsMargins(12, 6, 12, 12)
        idea_layout.setSpacing(7)
        setup.addWidget(idea_card)
        idea_layout.addWidget(QLabel("Ý tưởng / chủ đề:"))
        self.idea_input = QTextEdit()
        self.idea_input.setPlaceholderText(
            "VD: Ưu đãi phân bón hữu cơ mùa vụ mới cho bà con miền Tây, nhấn mạnh tăng năng suất và tiết kiệm chi phí"
        )
        self.idea_input.setFixedHeight(88)
        idea_layout.addWidget(self.idea_input)
        self.config_summary = QLabel()
        self.config_summary.setWordWrap(True)
        self.config_summary.setObjectName("mutedHint")
        idea_layout.addWidget(self.config_summary)
        self.run_btn = QPushButton("Chạy quy trình")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.clicked.connect(self._on_run_pipeline)
        idea_layout.addWidget(self.run_btn)

        self.timeline = TimelineWidget(["Viết nội dung", "Tạo ảnh / video", "Xuất bản"])
        self.timeline.layout().setSpacing(4)
        idea_layout.addWidget(self.timeline)
        self.content_step, self.asset_step, self.post_step = self.timeline.steps
        for step in self.timeline.steps:
            step.layout().setContentsMargins(8, 5, 8, 5)
            step.layout().setSpacing(8)
            step.content_layout.setSpacing(0)
            step.line.hide()
            step.line.setMinimumHeight(0)

        review_card, review_layout = card("2. Chỉnh sửa & media")
        review_layout.setContentsMargins(12, 6, 12, 12)
        review_layout.setSpacing(6)
        workspace.addWidget(review_card, 1)
        self.review_tabs = QTabWidget()
        review_layout.addWidget(self.review_tabs, 1)
        self.phone_panel, phone_layout = card("iPhone 12 · Facebook")
        phone_layout.setContentsMargins(8, 6, 8, 12)
        columns.addWidget(self.phone_panel, 0, Qt.AlignmentFlag.AlignRight)
        self.facebook_preview = FacebookPostPreview()
        def fit_preview_column(height):
            self.phone_panel.setFixedWidth(self.facebook_preview.width() + 16)

        self.facebook_preview.height_changed.connect(fit_preview_column)
        phone_layout.addWidget(self.facebook_preview, 1)
        self.facebook_preview.setToolTip("iPhone 12 · 390 × 844 · Tự co theo cửa sổ")
        self._build_content_step_extra()
        self._build_asset_step_extra()

        post_card, post_layout = card("3. Nơi đăng & xuất bản")
        post_layout.setContentsMargins(12, 6, 12, 12)
        post_layout.setSpacing(7)
        setup.addWidget(post_card)
        setup.addStretch(1)
        self._build_post_step_extra(post_layout)
        for button in self.findChildren(QPushButton):
            button.setFixedHeight(28)
        self._refresh_config_summary()

    def _build_content_step_extra(self) -> None:
        self.review_text = QTextEdit()
        self.review_text.setPlaceholderText("Nội dung sẽ hiển thị ở đây sau khi viết xong, có thể chỉnh sửa lại...")
        self.review_text.setMinimumHeight(200)
        self.review_text.textChanged.connect(
            lambda: self.facebook_preview.set_content(self.review_text.toPlainText())
        )
        self.review_tabs.addTab(self.review_text, "Chỉnh sửa")

    def _build_asset_step_extra(self) -> None:
        media_panel = QWidget()
        media_layout = QVBoxLayout(media_panel)
        media_layout.setContentsMargins(0, 0, 0, 0)
        self.image_selector = QComboBox()
        self.image_selector.setAccessibleName("Xem ảnh trong bài viết")
        self.image_selector.currentIndexChanged.connect(self._show_generated_image)
        self.image_selector.hide()
        media_layout.addWidget(self.image_selector)
        self.preview_label = MediaPreview("Ảnh hoặc video sẽ hiển thị tại đây sau khi tạo.")
        self.preview_label.setObjectName("mediaPreview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        media_layout.addWidget(self.preview_label, 1)
        self.review_tabs.addTab(media_panel, "Ảnh / video")

    def _show_generated_image(self, index: int) -> None:
        if 0 <= index < len(self._image_paths):
            pixmap = QPixmap(str(self._image_paths[index]))
            if not pixmap.isNull():
                self.preview_label.setPixmap(pixmap)

    def _build_post_step_extra(self, wl: QVBoxLayout) -> None:
        self.destinations_label = QLabel("Nền tảng và quyền riêng tư lấy từ Cài đặt quy trình.")
        self.destinations_label.setWordWrap(True)
        wl.addWidget(self.destinations_label)
        self.pages_selector = PagesSelectorWidget()
        self.pages_selector.layout().setSpacing(6)
        self.pages_selector.row_list.setFixedHeight(80)
        page_actions = self.pages_selector.layout().itemAt(1).layout()
        refresh_item = page_actions.takeAt(2)
        page_actions.addWidget(refresh_item.widget(), 0, 2)
        page_actions.setSpacing(4)
        self.pages_selector.selection_changed.connect(self._update_facebook_identity)
        wl.addWidget(self.pages_selector)

        schedule_row = QHBoxLayout()
        self.schedule_check = QCheckBox("Lên lịch Facebook")
        self.schedule_check.toggled.connect(lambda checked: self.schedule_datetime.setEnabled(checked))
        schedule_row.addWidget(self.schedule_check)
        self.schedule_datetime = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule_datetime.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.schedule_datetime.setCalendarPopup(True)
        self.schedule_datetime.setEnabled(False)
        self.schedule_check.toggled.connect(self._update_facebook_identity)
        self.schedule_datetime.dateTimeChanged.connect(self._update_facebook_identity)
        schedule_row.addWidget(self.schedule_datetime, 1)
        wl.addLayout(schedule_row)

        self.post_btn = QPushButton("Đăng bài")
        self.post_btn.setObjectName("primaryButton")
        self.post_btn.setEnabled(False)
        self.post_btn.clicked.connect(self._on_post)
        wl.addWidget(self.post_btn)
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setTextFormat(Qt.TextFormat.PlainText)
        wl.addWidget(self.result_label)

    def _update_facebook_identity(self, *_args) -> None:
        names = self.pages_selector.selected_names()
        scheduled = ""
        settings = self._run_settings or config.load_settings()
        if self.schedule_check.isChecked():
            scheduled = self.schedule_datetime.dateTime().toString("dd/MM/yyyy HH:mm")
        self.facebook_preview.set_page(names[0] if names else "Page Facebook", scheduled)

    def _refresh_config_summary(self) -> None:
        settings = self._run_settings or config.load_settings()
        platforms = selected_platforms(settings)
        attachment_labels = {ATTACHMENT_NONE: "Chỉ nội dung", ATTACHMENT_IMAGE: "Ảnh", ATTACHMENT_VIDEO: "Video"}
        attachment_labels[ATTACHMENT_IMAGE] = f"{settings.get('automation_image_count', 1)} ảnh / bài"
        mode = "Tự động đăng sau khi tạo" if settings.get("automation_auto_post", False) else "Duyệt trước khi đăng"
        self.config_summary.setText(
            "AI: " + PROVIDER_LABELS.get(settings.get("content_provider", "claude"), "AI")
            + " · " + attachment_labels.get(settings.get("automation_attachment", ATTACHMENT_IMAGE), "Ảnh")
            + "\nChế độ: " + mode
        )
        self.destinations_label.setText("Đăng lên: " + ", ".join(PLATFORM_LABELS[key] for key in platforms))
        facebook = "facebook" in platforms
        self.pages_selector.setVisible(facebook)
        self.schedule_check.setVisible(facebook)
        self.schedule_datetime.setVisible(facebook)
        if self._run_settings is None:
            self.pages_selector.set_selected_ids(settings.get("automation_facebook_page_ids", []))
        self._update_facebook_identity()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_config_summary()

    def _on_open_settings(self) -> None:
        self.settings_requested.emit()

    # ---------- Pipeline: content -> (image | video | skip) -> ready to review & post ----------

    def _on_run_pipeline(self) -> None:
        idea = self.idea_input.toPlainText().strip()
        if not idea:
            self.log_message.emit("Vui lòng nhập ý tưởng.", "error")
            return

        settings = config.load_settings()
        platforms = selected_platforms(settings)
        if any(key in platforms for key in ("tiktok", "youtube")) and settings.get("automation_attachment") != ATTACHMENT_VIDEO:
            self.log_message.emit("TikTok và YouTube cần đính kèm Video trong Cài đặt quy trình.", "error")
            return
        self._run_pages = configured_pages(settings) if "facebook" in platforms else []
        if settings.get("automation_auto_post", False):
            try:
                validate_destinations(settings, self._run_pages)
            except ValueError as exc:
                self.log_message.emit(str(exc), "error")
                return
        self._run_settings = deepcopy(settings)
        self._run_topic = idea
        self._refresh_config_summary()
        self._published_targets.clear()
        self.pages_selector.refresh()
        self.pages_selector.set_selected_ids(settings.get("automation_facebook_page_ids", []))
        self.pages_selector.setVisible("facebook" in platforms)
        self.schedule_check.setVisible("facebook" in platforms)
        self.schedule_datetime.setVisible("facebook" in platforms)
        self.destinations_label.setText("Đăng lên: " + ", ".join(PLATFORM_LABELS[key] for key in platforms))
        provider = settings.get("content_provider", "claude")
        tone = settings.get("automation_tone", "thân thiện, chuyên nghiệp")
        include_hashtags = bool(settings.get("automation_hashtags", True))
        attachment = settings.get("automation_attachment", ATTACHMENT_IMAGE)
        avatar_id = settings.get("heygen_avatar_id", "")
        voice_id = settings.get("heygen_voice_id", "")

        if attachment == ATTACHMENT_VIDEO and (not avatar_id or not voice_id):
            self.log_message.emit(
                "Chưa chọn Avatar/Voice mặc định cho Video — vào '⚙️ Cài đặt quy trình' để tải và chọn trước.",
                "error",
            )
            return

        try:
            client = get_text_client(provider)
        except ValueError as exc:
            self.log_message.emit(str(exc), "error")
            return

        self._content_text = ""
        self._image_path = None
        self._image_paths = []
        self.image_selector.clear()
        self.image_selector.hide()
        self._video_path = None
        self.review_tabs.setCurrentIndex(0)
        self.review_text.clear()
        self.facebook_preview.set_media()
        self.preview_label.clear()
        self.preview_label.setText("")
        self.result_label.setText("")
        self.post_btn.setEnabled(False)
        self.timeline.reset()

        self.run_btn.setEnabled(False)
        self._active_step = self.content_step
        self.content_step.set_status(STATUS_ACTIVE, "Đang viết content...")
        stages = [("content", "Viết content", "content"),
                  ("asset", "Tạo video" if attachment == ATTACHMENT_VIDEO else "Tạo ảnh", "video" if attachment == ATTACHMENT_VIDEO else "image")]
        if settings.get("automation_auto_post", False):
            stages.extend((key, f"Đăng {PLATFORM_LABELS[key]}", key) for key in platforms)
        self.processing_dialog.start("Đang viết content...", stages=stages)
        self.processing_dialog.set_stage("content")
        self.log_message.emit(f"Bắt đầu quy trình tự động với {PROVIDER_LABELS[provider]}...", "info")

        self._worker = Worker(
            client.generate_post,
            topic=idea,
            tone=tone,
            length="trung bình (80-150 từ)",
            audience="khách hàng đại chúng",
            include_hashtags=include_hashtags,
        )
        self._worker.finished.connect(
            lambda text: self._after_content(idea, text, attachment, provider, avatar_id, voice_id)
        )
        self._worker.error.connect(self._on_pipeline_error)
        self._worker.start()

    def _after_content(
        self, idea: str, content_text: str, attachment: str, provider: str, avatar_id: str, voice_id: str
    ) -> None:
        self._content_text = content_text
        self.review_text.setPlainText(content_text)
        history_store.add_content(idea, content_text)
        self.content_step.set_status(STATUS_DONE, "Đã viết xong — có thể chỉnh sửa lại bên trên.")
        self.log_message.emit("Đã viết xong content.", "success")
        self.processing_dialog.set_stage("content", "done")

        if attachment == ATTACHMENT_IMAGE:
            self.processing_dialog.set_stage("asset")
            self._active_step = self.asset_step
            self.asset_step.set_status(STATUS_ACTIVE, "Đang tạo prompt ảnh...")
            self.processing_dialog.set_status("Đang tạo prompt ảnh...")
            self._run_image_step(provider, content_text)
        elif attachment == ATTACHMENT_VIDEO:
            self.processing_dialog.set_stage("asset")
            self._active_step = self.asset_step
            self.asset_step.set_status(STATUS_ACTIVE, "Đang viết kịch bản video...")
            self.processing_dialog.set_status("Đang viết kịch bản video...")
            self._run_video_script_step(provider, content_text, avatar_id, voice_id)
        else:
            self.processing_dialog.set_stage("asset", "skipped")
            self.asset_step.set_status(STATUS_SKIPPED, "Bỏ qua (không đính kèm ảnh/video).")
            self._finish_pipeline()

    def _run_image_step(self, provider: str, content_text: str) -> None:
        try:
            text_client = get_text_client(provider)
        except ValueError as exc:
            self._on_pipeline_error(str(exc))
            return
        self._worker = Worker(text_client.suggest_image_prompt, content_text=content_text)
        self._worker.finished.connect(self._after_image_prompt)
        self._worker.error.connect(self._on_pipeline_error)
        self._worker.start()

    def _after_image_prompt(self, prompt: str) -> None:
        self.log_message.emit(f"Đã có prompt ảnh: {prompt}", "info")
        self._image_prompt = prompt
        self._generate_next_image()

    def _generate_next_image(self) -> None:
        settings = self._run_settings or config.load_settings()
        count = max(1, min(10, int(settings.get("automation_image_count", 1))))
        number = len(self._image_paths) + 1
        prompt = self._image_prompt
        if count > 1:
            prompt += (f"\nCreate image {number} of {count} for the same social media post. "
                       "Keep a consistent subject and visual style; use a distinct composition or viewpoint for this image.")
        try:
            image_client = ImageClient(config.get_secret("openai_api_key"), settings["openai_image_model"])
        except ValueError as exc:
            self._on_pipeline_error(str(exc))
            return
        self.asset_step.set_status(STATUS_ACTIVE, f"Đang tạo ảnh {number}/{count} với OpenAI…")
        self.processing_dialog.set_status(f"Đang tạo ảnh {number}/{count} với OpenAI…")
        self._worker = Worker(
            image_client.generate_image, prompt=prompt, size="1024x1024", dest_dir=config.output_dir("images")
        )
        self._worker.finished.connect(lambda path: self._after_image_done(prompt, path))
        self._worker.error.connect(self._on_pipeline_error)
        self._worker.start()

    def _after_image_done(self, prompt: str, path: Path) -> None:
        self._image_paths.append(path)
        self._image_path = self._image_paths[0]
        history_store.add_image(prompt, str(path))
        self.image_selector.addItem(f"Ảnh {len(self._image_paths)} · {path.name}")
        self.image_selector.setCurrentIndex(len(self._image_paths) - 1)
        self.image_selector.setVisible(len(self._image_paths) > 1)
        self.log_message.emit(f"Đã tạo ảnh: {path}", "success")
        settings = self._run_settings or config.load_settings()
        count = max(1, min(10, int(settings.get("automation_image_count", 1))))
        self.facebook_preview.set_media(QPixmap(str(self._image_path)), image_count=len(self._image_paths))
        if len(self._image_paths) < count:
            self._generate_next_image()
            return
        self.asset_step.set_status(STATUS_DONE, f"Đã tạo đủ {count}/{count} ảnh cho bài viết.")
        self.processing_dialog.set_stage("asset", "done")
        self._finish_pipeline()

    def _run_video_script_step(self, provider: str, content_text: str, avatar_id: str, voice_id: str) -> None:
        try:
            text_client = get_text_client(provider)
        except ValueError as exc:
            self._on_pipeline_error(str(exc))
            return
        self._worker = Worker(text_client.suggest_video_script, content_text=content_text)
        self._worker.finished.connect(lambda script: self._after_video_script(script, avatar_id, voice_id))
        self._worker.error.connect(self._on_pipeline_error)
        self._worker.start()

    def _after_video_script(self, script: str, avatar_id: str, voice_id: str) -> None:
        self.log_message.emit("Đã có kịch bản, đang tạo video với HeyGen (có thể mất vài phút)...", "info")
        try:
            heygen_client = HeyGenClient(config.get_secret("heygen_api_key"))
        except ValueError as exc:
            self._on_pipeline_error(str(exc))
            return
        self.asset_step.set_status(STATUS_ACTIVE, "Đang tạo video với HeyGen...")
        self.processing_dialog.set_status("Đang tạo video với HeyGen (có thể mất vài phút)...")
        self._worker = Worker(
            heygen_client.generate_and_wait,
            avatar_id=avatar_id,
            voice_id=voice_id,
            script_text=script,
            dest_dir=config.output_dir("videos"),
        )
        self._worker.progress.connect(lambda msg: self.asset_step.set_status(STATUS_ACTIVE, msg))
        self._worker.progress.connect(self.processing_dialog.set_status)
        self._worker.thumbnail.connect(self._on_thumbnail_ready)
        self._worker.finished.connect(lambda path: self._after_video_done(script, path))
        self._worker.error.connect(self._on_pipeline_error)
        self._worker.start()

    def _on_thumbnail_ready(self, url: str) -> None:
        # A real frame from the video HeyGen is rendering — show it instead of leaving the
        # preview blank while the (multi-minute) generation is still in progress.
        self._thumbnail_worker = Worker(self._fetch_image_bytes, url)
        self._thumbnail_worker.finished.connect(self._on_thumbnail_image_loaded)
        self._thumbnail_worker.error.connect(lambda _msg: None)  # a missed preview frame is not worth alarming over
        self._thumbnail_worker.start()

    @staticmethod
    def _fetch_image_bytes(url: str) -> bytes:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.content

    def _on_thumbnail_image_loaded(self, data: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.preview_label.setPixmap(pixmap)
            self.facebook_preview.set_media(pixmap, "Video đang được tạo")

    def _after_video_done(self, script: str, path: Path) -> None:
        self._video_path = path
        history_store.add_video(script, str(path))
        self.preview_label.setText(f"🎬 Video đã tạo:\n{path}")
        self.facebook_preview.finish_video(path.name)
        self.asset_step.set_status(STATUS_DONE, f"Đã tạo video: {path.name}")
        self.log_message.emit(f"Đã tạo video: {path}", "success")
        self.processing_dialog.set_stage("asset", "done")
        self._finish_pipeline()

    def _finish_pipeline(self) -> None:
        self.post_btn.setEnabled(True)

        if bool((self._run_settings or {}).get("automation_auto_post", False)):
            self.post_step.set_status(STATUS_ACTIVE, "Đã bật tự động đăng ngay — đang đăng bài, bỏ qua bước duyệt...")
            self.processing_dialog.set_status("Đã tạo xong nội dung — đang tự động đăng bài...")
            self.log_message.emit(
                "Quy trình tạo xong — chế độ tự động đăng đang bật nên bỏ qua bước chờ duyệt.", "info"
            )
            self._on_post(auto=True)
            return

        self.run_btn.setEnabled(True)
        self.post_step.set_status(STATUS_ACTIVE, "Xem lại nội dung rồi bấm Đăng bài theo cấu hình của lần chạy.")
        self.processing_dialog.finish("Đã tạo xong nội dung — xem lại và bấm Đăng bài khi sẵn sàng.")
        self.log_message.emit("Quy trình tự động hoàn tất, sẵn sàng đăng bài.", "success")

    def _on_pipeline_error(self, message: str) -> None:
        self.run_btn.setEnabled(True)
        target = self._active_step or self.content_step
        target.set_status(STATUS_ERROR, f"Lỗi: {message}")
        self.processing_dialog.finish(f"Lỗi: {message}", outcome="error")
        self.log_message.emit(f"Lỗi trong quy trình tự động: {message}", "error")

    # ---------- Posting ----------

    def _on_post(self, auto: bool = False) -> None:
        message = self.review_text.toPlainText().strip()
        settings = self._run_settings
        if settings is None:
            self.log_message.emit("Chạy quy trình để tạo nội dung trước khi đăng.", "error")
            return
        pages = self._run_pages if auto else self.pages_selector.selected_pages()
        try:
            validate_destinations(settings, pages)
            if settings.get("automation_attachment") == ATTACHMENT_NONE and not message:
                raise ValueError("Nội dung bài đăng đang trống.")
        except ValueError as exc:
            self._on_post_error(str(exc))
            return
        platforms = selected_platforms(settings)
        scheduled_time = None
        schedule_label = ""
        if "facebook" in platforms and self.schedule_check.isChecked():
            dt: datetime = self.schedule_datetime.dateTime().toPython()
            if dt < datetime.now() + timedelta(minutes=10):
                self._on_post_error("Facebook cần lịch đăng ít nhất 10 phút sau hiện tại.")
                return
            scheduled_time = int(dt.timestamp())
            schedule_label = dt.isoformat(timespec="minutes")
        if not auto:
            names = [PLATFORM_LABELS[key] for key in platforms]
            if "facebook" in platforms:
                names.append("Page: " + ", ".join(page["name"] for page in pages))
            if "tiktok" in platforms:
                names.append("TikTok: " + settings.get("automation_tiktok_privacy", "SELF_ONLY"))
            if "youtube" in platforms:
                names.append("YouTube: " + settings.get("automation_youtube_privacy", "private"))
            if scheduled_time:
                names.append("Lịch Facebook: " + schedule_label + "; TikTok/YouTube đăng ngay")
            if QMessageBox.question(self, "Đăng bài theo cấu hình", "Đăng nội dung lên " + "; ".join(names) + "?") != QMessageBox.StandardButton.Yes:
                return
        self.run_btn.setEnabled(False)
        self.post_btn.setEnabled(False)
        self.review_text.setReadOnly(True)
        self.pages_selector.setEnabled(False)
        self.schedule_check.setEnabled(False)
        self.schedule_datetime.setEnabled(False)
        self.result_label.clear()
        self.post_step.set_status(STATUS_ACTIVE, "Đang đăng bài theo cấu hình...")
        if auto and self.processing_dialog.scene.running:
            self.processing_dialog.set_status("Đang đăng bài theo cấu hình...")
        else:
            stages = [(key, f"Đăng {PLATFORM_LABELS[key]}", key) for key in platforms]
            self.processing_dialog.start("Đang đăng bài theo cấu hình...", stages=stages)
        from app.core.automation_publisher import publish_and_archive
        self._worker = Worker(publish_and_archive, settings=deepcopy(settings), message=message,
            topic=self._run_topic, pages=deepcopy(pages), image_path=self._image_path,
            image_paths=list(self._image_paths) or None,
            video_path=self._video_path, scheduled_time=scheduled_time,
            skip_targets=set(self._published_targets))
        self._worker.progress.connect(lambda msg: self.post_step.set_status(STATUS_ACTIVE, msg))
        self._worker.progress.connect(self.processing_dialog.set_status)
        self._worker.stage.connect(self.processing_dialog.set_stage)
        self._worker.finished.connect(lambda results: self._on_post_done(message, schedule_label, results))
        self._worker.error.connect(self._on_post_error)
        self._worker.start()

    def _unlock_posting(self) -> None:
        self.run_btn.setEnabled(True)
        self.post_btn.setEnabled(True)
        self.review_text.setReadOnly(False)
        self.pages_selector.setEnabled(True)
        self.schedule_check.setEnabled(True)
        self.schedule_datetime.setEnabled(self.schedule_check.isChecked())

    def _on_post_done(self, message: str, schedule_label: str, results: list[dict]) -> None:
        self._unlock_posting()
        lines = []
        for result in results:
            name = result['name']
            if result['ok']:
                self._published_targets.add(result['target'])
                outcome = f"đã nhận lịch {schedule_label}, chờ đăng" if schedule_label and result['platform'] == 'facebook' else "thành công"
                line = f"✓ {name}: {outcome}" + (f" (id={result['post_id']})" if result.get('post_id') else "")
                self.log_message.emit(line, "success")
            else:
                line = f"✗ {name}: {result.get('error', 'Đăng thất bại')}"
                if result.get('uncertain'):
                    self._published_targets.add(result['target'])
                    line += " · Tạm bỏ qua khi thử lại để tránh trùng bài; kiểm tra Page."
                self.log_message.emit(line, "error")
            lines.append(line)
            if result.get('archive_error'):
                warning = f"{name}: đã xử lý đăng nhưng chưa lưu đủ vào kho: {result['archive_error']}"
                lines.append(warning)
                self.log_message.emit(warning, "error")
        failures = sum(not result['ok'] for result in results)
        uncertain = sum(bool(result.get('uncertain')) for result in results)
        if not results:
            summary = "Các nơi đã thành công hoặc chưa xác nhận được bỏ qua để tránh đăng trùng."
        else:
            summary = f"Hoàn tất: {len(results) - failures} thành công, {failures - uncertain} thất bại."
            if uncertain:
                summary += f" {uncertain} bài chưa xác nhận; kiểm tra Page trước khi đăng lại."
        archive_failures = sum(bool(result.get('archive_error')) for result in results)
        if archive_failures:
            summary += f" {archive_failures} bài chưa lưu đủ vào kho; xem chi tiết bên dưới."
        self.post_step.set_status(STATUS_ERROR if failures else STATUS_DONE, summary)
        self.processing_dialog.finish(summary, outcome="error" if failures else "done")
        self.result_label.setText("\n".join(lines) or summary)

    def _on_post_error(self, message: str) -> None:
        self._unlock_posting()
        self.post_step.set_status(STATUS_ERROR, f"Lỗi: {message}")
        self.processing_dialog.finish(f"Lỗi đăng bài: {message}", outcome="error")
        self.result_label.setText(message)
        self.log_message.emit(f"Lỗi đăng bài: {message}", "error")
