"""Tab 1: viết content bằng Claude hoặc OpenAI."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.text_provider import PROVIDER_CLAUDE, PROVIDER_LABELS, PROVIDER_OPENAI, get_text_client
from app.core.content_prompts import get_post_system_prompt
from app.storage import history_store
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.ui.widgets.liquid_glass import GlassCard
from app.ui.widgets.post_prompt_editor import PostPromptEditor
from app.workers.async_worker import Worker


class ContentTab(QWidget):
    use_for_image = Signal(str)
    use_for_video = Signal(str)
    use_for_post = Signal(str)
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Worker | None = None
        self._generating = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(
            make_page_header("📝 Viết Content", "Soạn nội dung bài đăng Facebook bằng AI, sẵn sàng dùng cho ảnh/video/đăng bài.")
        )

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Nhà cung cấp viết content:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem(PROVIDER_LABELS[PROVIDER_CLAUDE], PROVIDER_CLAUDE)
        self.provider_combo.addItem(PROVIDER_LABELS[PROVIDER_OPENAI], PROVIDER_OPENAI)
        default_provider = config.load_settings().get("content_provider", PROVIDER_CLAUDE)
        idx = self.provider_combo.findData(default_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        provider_row.addWidget(self.provider_combo, 1)
        layout.addLayout(provider_row)

        layout.addWidget(QLabel("Chủ đề / ý tưởng bài đăng:"))
        self.topic_input = QLineEdit()
        self.topic_input.setPlaceholderText("VD: Ưu đãi phân bón hữu cơ mùa vụ mới cho bà con miền Tây")
        layout.addWidget(self.topic_input)

        row = QFormLayout()
        self.tone_combo = QComboBox()
        self.tone_combo.addItems(
            ["thân thiện, chuyên nghiệp", "hài hước, gần gũi", "trang trọng", "thúc đẩy hành động (khuyến mãi)"]
        )
        row.addRow("Giọng điệu:", self.tone_combo)
        self.length_combo = QComboBox()
        self.length_combo.addItems(["ngắn (30-60 từ)", "trung bình (80-150 từ)", "dài (200-300 từ)"])
        self.length_combo.setCurrentIndex(1)
        row.addRow("Độ dài:", self.length_combo)

        self.hashtag_check = QCheckBox("Thêm hashtag")
        self.hashtag_check.setChecked(True)
        row.addRow("", self.hashtag_check)
        layout.addLayout(row)

        layout.addWidget(QLabel("Đối tượng đọc:"))
        self.audience_input = QLineEdit("khách hàng đại chúng")
        layout.addWidget(self.audience_input)

        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Số lượng content cho ý tưởng này (1-10):"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 10)
        self.count_spin.setValue(1)
        self.count_spin.valueChanged.connect(self._on_count_changed)
        count_row.addWidget(self.count_spin)
        count_row.addStretch(1)
        layout.addLayout(count_row)

        self.prompt_editor = PostPromptEditor()
        self.prompt_editor.log_message.connect(self.log_message.emit)
        self.prompt_editor.busy_changed.connect(self._on_prompt_busy)
        layout.addWidget(self.prompt_editor)

        self.generate_btn = QPushButton("Viết content")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.clicked.connect(self._on_generate)
        layout.addWidget(self.generate_btn)

        layout.addWidget(QLabel("Kết quả (có thể chỉnh sửa):"))
        self.result_text = QTextEdit()
        layout.addWidget(self.result_text)

        self.variants_scroll = QScrollArea()
        self.variants_scroll.setWidgetResizable(True)
        self.variants_scroll.setFixedHeight(360)
        self.variants_scroll.setVisible(False)
        variants_container = QWidget()
        self.variants_layout = QVBoxLayout(variants_container)
        self.variants_layout.setSpacing(10)
        self.variants_layout.addStretch(1)
        self.variants_scroll.setWidget(variants_container)
        layout.addWidget(self.variants_scroll)

        actions = QVBoxLayout()
        self.to_image_btn = QPushButton("→ Dùng cho tab Ảnh")
        self.to_video_btn = QPushButton("→ Dùng cho tab Video")
        self.to_post_btn = QPushButton("→ Dùng cho tab Đăng Facebook")
        for b in (self.to_image_btn, self.to_video_btn, self.to_post_btn):
            b.setObjectName("linkButton")
        self.to_image_btn.clicked.connect(lambda: self.use_for_image.emit(self.result_text.toPlainText()))
        self.to_video_btn.clicked.connect(lambda: self.use_for_video.emit(self.result_text.toPlainText()))
        self.to_post_btn.clicked.connect(lambda: self.use_for_post.emit(self.result_text.toPlainText()))
        for b in (self.to_image_btn, self.to_video_btn, self.to_post_btn):
            actions.addWidget(b)
        layout.addLayout(actions)
        self.result_text.setPlaceholderText("Nội dung được tạo sẽ xuất hiện ở đây. Bạn có thể chỉnh sửa trước khi sử dụng.")
        arrange_cards(layout, [("Thông tin bài viết", list(range(9))), ("Bản thảo", [9, 10, 11, 12])])

    def _on_prompt_busy(self, busy: bool) -> None:
        self.generate_btn.setEnabled(not busy and not self._generating)

    def _on_count_changed(self, value: int) -> None:
        self.generate_btn.setText("Viết content" if value <= 1 else f"Viết {value} content")

    def _on_generate(self) -> None:
        if self.prompt_editor.busy or self._generating:
            return
        if self.prompt_editor.dirty:
            self.log_message.emit("Lưu prompt đã chỉnh vào DB trước khi viết content.", "error")
            return
        topic = self.topic_input.text().strip()
        if not topic:
            self.log_message.emit("Vui lòng nhập chủ đề bài đăng.", "error")
            return

        provider = self.provider_combo.currentData()
        try:
            client = get_text_client(provider)
        except ValueError as exc:
            self.log_message.emit(str(exc), "error")
            return

        settings = config.load_settings()
        settings["content_provider"] = provider
        config.save_settings(settings)

        count = self.count_spin.value()
        gen_kwargs = dict(
            topic=topic,
            tone=self.tone_combo.currentText(),
            length=self.length_combo.currentText(),
            audience=self.audience_input.text().strip() or "khách hàng đại chúng",
            include_hashtags=self.hashtag_check.isChecked(),
        )

        self.generate_btn.setEnabled(False)
        self._generating = True
        self.prompt_editor.setEnabled(False)
        self._clear_variants()

        if count <= 1:
            self.log_message.emit(f"Đang gọi {PROVIDER_LABELS[provider]} để viết content...", "info")
            self._worker = Worker(client.generate_post, **gen_kwargs)
            self._worker.finished.connect(lambda text: self._on_done(topic, [text]))
        else:
            self.log_message.emit(f"Đang tạo {count} phiên bản content với {PROVIDER_LABELS[provider]}...", "info")
            self._worker = Worker(self._generate_batch, client=client, count=count, **gen_kwargs)
            self._worker.progress.connect(lambda msg: self.log_message.emit(msg, "info"))
            self._worker.finished.connect(lambda texts: self._on_done(topic, texts))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @staticmethod
    def _generate_batch(client, count: int, on_progress=None, **kwargs) -> list[str]:
        kwargs["system_prompt"] = get_post_system_prompt()
        results = []
        for i in range(count):
            if on_progress:
                on_progress(f"Đang tạo phiên bản {i + 1}/{count}...")
            results.append(client.generate_post(**kwargs))
        return results

    def _on_done(self, topic: str, texts: list[str]) -> None:
        self._generating = False
        self.prompt_editor.setEnabled(True)
        self.generate_btn.setEnabled(True)
        for text in texts:
            history_store.add_content(topic, text)
        self.result_text.setPlainText(texts[0])
        if len(texts) > 1:
            self._populate_variants(texts)
            self.log_message.emit(
                f"Đã tạo xong {len(texts)} phiên bản — chọn 1 bản bên dưới để dùng cho ảnh/video/đăng bài.",
                "success",
            )
        else:
            self.log_message.emit("Đã tạo content xong.", "success")

    def _on_error(self, message: str) -> None:
        self._generating = False
        self.prompt_editor.setEnabled(True)
        self.generate_btn.setEnabled(True)
        self.log_message.emit(f"Lỗi tạo content: {message}", "error")

    def _clear_variants(self) -> None:
        while self.variants_layout.count() > 1:  # keep the trailing stretch at the end
            item = self.variants_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.variants_scroll.setVisible(False)

    def _populate_variants(self, texts: list[str]) -> None:
        self._clear_variants()
        for index, text in enumerate(texts, start=1):
            card = GlassCard()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 16, 16, 18)
            card_layout.setSpacing(6)
            title = QLabel(f"Phiên bản {index}")
            title.setObjectName("sectionTitle")
            card_layout.addWidget(title)
            preview = QTextEdit()
            preview.setPlainText(text)
            preview.setFixedHeight(130)
            card_layout.addWidget(preview)
            use_btn = QPushButton("→ Dùng bản này")
            use_btn.setObjectName("linkButton")
            use_btn.clicked.connect(lambda _checked=False, p=preview: self._on_use_variant(p))
            card_layout.addWidget(use_btn)
            self.variants_layout.insertWidget(self.variants_layout.count() - 1, card)
        self.variants_scroll.setVisible(True)

    def _on_use_variant(self, preview: QTextEdit) -> None:
        self.result_text.setPlainText(preview.toPlainText())
        self.log_message.emit("Đã chọn phiên bản này để dùng cho ảnh/video/đăng bài.", "info")
