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
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.automation_publisher import configured_pages, publish_generated, selected_platforms, validate_destinations, PLATFORM_LABELS
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

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
        columns.setSpacing(20)
        layout.addLayout(columns, 1)
        idea_card, idea_layout = card("Ý tưởng khởi đầu")
        columns.addWidget(idea_card, 1)

        idea_layout.addWidget(QLabel("Ý tưởng / chủ đề:"))
        self.idea_input = QTextEdit()
        self.idea_input.setPlaceholderText(
            "VD: Ưu đãi phân bón hữu cơ mùa vụ mới cho bà con miền Tây, nhấn mạnh tăng năng suất và tiết kiệm chi phí"
        )
        self.idea_input.setFixedHeight(160)
        idea_layout.addWidget(self.idea_input)

        self.run_btn = QPushButton("Chạy quy trình tự động")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.clicked.connect(self._on_run_pipeline)
        idea_layout.addWidget(self.run_btn)
        idea_layout.addStretch(1)

        progress_card, progress_layout = card("Tiến trình & duyệt bài")
        columns.addWidget(progress_card, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        progress_layout.addWidget(scroll, 1)
        self.timeline = TimelineWidget(["Viết Content", "Tạo Ảnh / Video", "Đăng bài"])
        scroll.setWidget(self.timeline)
        self.content_step, self.asset_step, self.post_step = self.timeline.steps

        self._build_content_step_extra()
        self._build_asset_step_extra()
        self._build_post_step_extra()

    def _build_content_step_extra(self) -> None:
        self.review_text = QTextEdit()
        self.review_text.setPlaceholderText("Nội dung sẽ hiển thị ở đây sau khi viết xong, có thể chỉnh sửa lại...")
        self.review_text.setMinimumHeight(120)
        self.content_step.set_extra_widget(self.review_text)

    def _build_asset_step_extra(self) -> None:
        self.preview_label = MediaPreview("Ảnh hoặc video sẽ hiển thị tại đây sau khi tạo.")
        self.preview_label.setObjectName("mediaPreview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(160)
        self.asset_step.set_extra_widget(self.preview_label)

    def _build_post_step_extra(self) -> None:
        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(8)

        self.pages_selector = PagesSelectorWidget()
        wl.addWidget(self.pages_selector)
        self.destinations_label = QLabel("Nền tảng và quyền riêng tư lấy từ Cài đặt quy trình.")
        self.destinations_label.setWordWrap(True)
        wl.addWidget(self.destinations_label)

        schedule_row = QVBoxLayout()
        self.schedule_check = QCheckBox("Lên lịch Facebook")
        self.schedule_check.toggled.connect(lambda checked: self.schedule_datetime.setEnabled(checked))
        schedule_row.addWidget(self.schedule_check)
        self.schedule_datetime = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule_datetime.setCalendarPopup(True)
        self.schedule_datetime.setEnabled(False)
        schedule_row.addWidget(self.schedule_datetime)
        wl.addLayout(schedule_row)

        self.post_btn = QPushButton("Đăng bài")
        self.post_btn.setObjectName("primaryButton")
        self.post_btn.setEnabled(False)
        self.post_btn.clicked.connect(self._on_post)
        wl.addWidget(self.post_btn)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        wl.addWidget(self.result_label)

        self.post_step.set_extra_widget(wrapper)

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
        self._video_path = None
        self.review_text.clear()
        self.preview_label.clear()
        self.preview_label.setText("")
        self.result_label.setText("")
        self.post_btn.setEnabled(False)
        self.timeline.reset()

        self.run_btn.setEnabled(False)
        self._active_step = self.content_step
        self.content_step.set_status(STATUS_ACTIVE, "Đang viết content...")
        self.processing_dialog.start("Đang viết content...")
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

        if attachment == ATTACHMENT_IMAGE:
            self._active_step = self.asset_step
            self.asset_step.set_status(STATUS_ACTIVE, "Đang tạo prompt ảnh...")
            self.processing_dialog.set_status("Đang tạo prompt ảnh...")
            self._run_image_step(provider, content_text)
        elif attachment == ATTACHMENT_VIDEO:
            self._active_step = self.asset_step
            self.asset_step.set_status(STATUS_ACTIVE, "Đang viết kịch bản video...")
            self.processing_dialog.set_status("Đang viết kịch bản video...")
            self._run_video_script_step(provider, content_text, avatar_id, voice_id)
        else:
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
        settings = config.load_settings()
        try:
            image_client = ImageClient(config.get_secret("openai_api_key"), settings["openai_image_model"])
        except ValueError as exc:
            self._on_pipeline_error(str(exc))
            return
        self.asset_step.set_status(STATUS_ACTIVE, "Đang tạo ảnh với OpenAI...")
        self.processing_dialog.set_status("Đang tạo ảnh với OpenAI...")
        self._worker = Worker(
            image_client.generate_image, prompt=prompt, size="1024x1024", dest_dir=config.output_dir("images")
        )
        self._worker.finished.connect(lambda path: self._after_image_done(prompt, path))
        self._worker.error.connect(self._on_pipeline_error)
        self._worker.start()

    def _after_image_done(self, prompt: str, path: Path) -> None:
        self._image_path = path
        history_store.add_image(prompt, str(path))
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            self.preview_label.setPixmap(pixmap)
        self.asset_step.set_status(STATUS_DONE, f"Đã tạo ảnh: {path.name}")
        self.log_message.emit(f"Đã tạo ảnh: {path}", "success")
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

    def _after_video_done(self, script: str, path: Path) -> None:
        self._video_path = path
        history_store.add_video(script, str(path))
        self.preview_label.setText(f"🎬 Video đã tạo:\n{path}")
        self.asset_step.set_status(STATUS_DONE, f"Đã tạo video: {path.name}")
        self.log_message.emit(f"Đã tạo video: {path}", "success")
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
        self.processing_dialog.finish(f"Lỗi: {message}")
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
        if "facebook" in platforms and self.schedule_check.isChecked() and not auto:
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
        self.processing_dialog.start("Đang đăng bài theo cấu hình...")
        self._worker = Worker(publish_generated, settings=deepcopy(settings), message=message,
            topic=self._run_topic, pages=deepcopy(pages), image_path=self._image_path,
            video_path=self._video_path, scheduled_time=scheduled_time,
            skip_targets=set(self._published_targets))
        self._worker.progress.connect(lambda msg: self.post_step.set_status(STATUS_ACTIVE, msg))
        self._worker.progress.connect(self.processing_dialog.set_status)
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
                line = f"✓ {name}: thành công" + (f" (id={result['post_id']})" if result.get('post_id') else "")
                self.log_message.emit(line, "success")
            else:
                line = f"✗ {name}: {result.get('error', 'Đăng thất bại')}"
                self.log_message.emit(line, "error")
            lines.append(line)
            history_store.add_post(result['post_type'], message, result.get('attachment_path', ''),
                schedule_label if result['platform'] == 'facebook' else '', result.get('post_id', ''),
                page_id=result.get('id', ''), page_name=name, ok=result['ok'])
        failures = sum(not result['ok'] for result in results)
        if not results:
            summary = "Các nơi đã đăng thành công được bỏ qua để tránh đăng trùng."
        else:
            summary = f"Hoàn tất: {len(results) - failures} thành công, {failures} thất bại."
        self.post_step.set_status(STATUS_ERROR if failures else STATUS_DONE, summary)
        self.processing_dialog.finish(summary)
        self.result_label.setText("\n".join(lines) or summary)

    def _on_post_error(self, message: str) -> None:
        self._unlock_posting()
        self.post_step.set_status(STATUS_ERROR, f"Lỗi: {message}")
        self.processing_dialog.finish(f"Lỗi đăng bài: {message}")
        self.result_label.setText(message)
        self.log_message.emit(f"Lỗi đăng bài: {message}", "error")
