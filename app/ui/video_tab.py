"""Tab 3: tạo video avatar nói bằng HeyGen, hoặc video từ mô tả bằng Grok (xAI)."""
from __future__ import annotations

import threading
from pathlib import Path

import requests
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.heygen_client import HeyGenClient
from app.core.image_client import ImageClient
from app.core.grok_video_client import (
    ASPECT_RATIOS,
    IMAGE_FILE_FILTER,
    MAX_REFERENCE_IMAGES,
    RESOLUTIONS,
    GrokVideoClient,
)
from app.core.transcription_client import SAMPLE_FILE_FILTER, TranscriptionClient
from app.core.text_provider import PROVIDER_CLAUDE, get_text_client
from app.core.video_prompt import create_video_prompt, compose_video_prompt
from app.storage import history_store
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import card
from app.ui.widgets.media_preview import MediaPreview
from app.ui.widgets.image_editor import ImageEditorDialog
from app.workers.async_worker import Worker
from app.ui.widgets.processing_dialog import ProcessingDialog

PROVIDER_HEYGEN = "heygen"
PROVIDER_GROK = "grok"


class VideoTab(QWidget):
    video_generated = Signal(Path)
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._content_context = ""
        self._prompt_source = None
        self._current_video_path: Path | None = None
        self._reference_image_path: Path | None = None
        self._reference_video_path: Path | None = None
        self._reference_busy = False
        self._asset_busy = False
        self._asset_sample_path: Path | None = None
        self._product_image_path: Path | None = None
        self._asset_face_path: Path | None = None
        self._asset_versions: dict[Path, list[tuple[Path, str]]] = {}
        self._workflow_busy = False
        self._selected_asset_path: Path | None = None
        self._show_video_result = False
        self._material_image_paths: list[Path] = []
        self._avatar_previews: dict[str, str] = {}
        self._worker: Worker | None = None
        self._preview_worker: Worker | None = None
        self._cancel_event: threading.Event | None = None
        self._build_ui()
        self.processing_dialog = ProcessingDialog(self)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(make_page_header("🎬 Tạo Video", "Tạo vật liệu, viết kịch bản dựa trên ảnh, rồi dựng video."))

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Nhà cung cấp:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("HeyGen (Avatar nói kịch bản)", PROVIDER_HEYGEN)
        self.provider_combo.addItem("Grok (xAI - tạo video từ mô tả)", PROVIDER_GROK)
        provider_row.addWidget(self.provider_combo, 1)
        layout.addLayout(provider_row)

        self.step_indicator = QWidget()
        steps = QHBoxLayout(self.step_indicator)
        steps.setContentsMargins(0, 0, 0, 0)
        self.step_labels = []
        for title in ("Vật liệu", "Kịch bản", "Tạo video"):
            label = QLabel(title)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(38)
            steps.addWidget(label, 1)
            self.step_labels.append(label)
        layout.addWidget(self.step_indicator)

        panels = QHBoxLayout()
        panels.setSpacing(20)
        editor_card, editor = card("Kịch bản")
        self.editor_title = editor_card.findChild(QLabel, "cardTitle")
        preview_card, preview_body = card("Hướng dẫn")
        self.preview_title = preview_card.findChild(QLabel, "cardTitle")
        panels.addWidget(editor_card, 1)
        panels.addWidget(preview_card, 1)
        layout.addLayout(panels, 1)

        self.workflow_stack = QStackedWidget()
        editor.addWidget(self.workflow_stack, 1)
        self.script_page = QWidget()
        script_layout = QVBoxLayout(self.script_page)
        script_layout.setContentsMargins(0, 0, 0, 0)
        self.preparation_page = QWidget()
        preparation_layout = QVBoxLayout(self.preparation_page)
        preparation_layout.setContentsMargins(0, 0, 0, 0)
        self.render_page = QWidget()
        render_layout = QVBoxLayout(self.render_page)
        render_layout.setContentsMargins(0, 0, 0, 0)
        for page in (self.preparation_page, self.script_page, self.render_page):
            self.workflow_stack.addWidget(page)

        self.load_avatars_btn = QPushButton("Tải My Avatar / My Voice từ HeyGen")
        self.load_avatars_btn.setObjectName("linkButton")
        self.load_avatars_btn.clicked.connect(self._on_load_avatars)
        script_layout.addWidget(self.load_avatars_btn)
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
        script_layout.addWidget(self.heygen_options)

        self.script_label = QLabel("Kịch bản video:")
        script_layout.addWidget(self.script_label)
        self.script_material_context = QLabel()
        self.script_material_context.setWordWrap(True)
        self.script_material_context.setObjectName("mutedHint")
        script_layout.addWidget(self.script_material_context)
        self.script_input = QTextEdit()
        self.script_input.setMinimumHeight(140)
        script_layout.addWidget(self.script_input, 1)
        self.create_prompt_btn = QPushButton("Tạo prompt từ kịch bản")
        self.create_prompt_btn.setObjectName("linkButton")
        self.create_prompt_btn.clicked.connect(self._on_create_video_prompt)
        script_layout.addWidget(self.create_prompt_btn)
        self.video_prompt_input = QTextEdit()
        self.video_prompt_input.setPlaceholderText("Prompt dựng video (tùy chọn). Tạo từ kịch bản hoặc nhập chỉ dẫn của bạn tại đây.")
        self.video_prompt_input.setMaximumHeight(150)
        script_layout.addWidget(self.video_prompt_input)
        self.video_prompt_hint = QLabel("Có thể chỉnh prompt trước khi tạo video. HeyGen sẽ dùng Video Agent khi có prompt.")
        self.video_prompt_hint.setWordWrap(True)
        self.video_prompt_hint.setObjectName("mutedHint")
        script_layout.addWidget(self.video_prompt_hint)
        self.reference_toggle = QPushButton("Lấy ý tưởng từ video mẫu (tùy chọn)")
        self.reference_toggle.setObjectName("linkButton")
        self.reference_toggle.setCheckable(True)
        script_layout.addWidget(self.reference_toggle)
        self.reference_panel = QWidget()
        reference_layout = QVBoxLayout(self.reference_panel)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        reference_actions = QHBoxLayout()
        self.reference_video_btn = QPushButton("Chọn video mẫu")
        self.reference_video_btn.setObjectName("linkButton")
        self.reference_video_btn.clicked.connect(self._on_attach_reference_video)
        reference_actions.addWidget(self.reference_video_btn, 1)
        self.analyze_reference_btn = QPushButton("Phân tích")
        self.analyze_reference_btn.setObjectName("linkButton")
        self.analyze_reference_btn.setEnabled(False)
        self.analyze_reference_btn.clicked.connect(self._on_analyze_reference_video)
        reference_actions.addWidget(self.analyze_reference_btn)
        reference_layout.addLayout(reference_actions)
        self.reference_video_label = QLabel("Chọn video mẫu để chuyển ý tưởng từ lời thoại thành kịch bản.")
        self.reference_video_label.setObjectName("mutedHint")
        self.reference_video_label.setWordWrap(True)
        reference_layout.addWidget(self.reference_video_label)
        script_layout.addWidget(self.reference_panel)
        self.reference_panel.hide()
        self.reference_toggle.toggled.connect(self.reference_panel.setVisible)
        self.back_material_btn = QPushButton("← Quay lại chỉnh vật liệu")
        self.back_material_btn.setObjectName("linkButton")
        self.back_material_btn.clicked.connect(lambda: self._go_to_step(0))
        script_layout.addWidget(self.back_material_btn)
        self.script_next_btn = QPushButton("Tiếp tục → Kiểm tra và tạo video")
        self.script_next_btn.setObjectName("primaryButton")
        self.script_next_btn.clicked.connect(self._on_script_next)
        script_layout.addWidget(self.script_next_btn)

        preparation_layout.addWidget(QLabel("Bối cảnh, nhân vật và phong cách hình ảnh"))
        self.scene_input = QTextEdit()
        self.scene_input.setPlaceholderText("VD: Nhân vật áo trắng, phòng livestream, ánh sáng ấm; sản phẩm đặt trên bàn gỗ.")
        self.scene_input.setMinimumHeight(85)
        self.scene_input.setMaximumHeight(130)
        preparation_layout.addWidget(self.scene_input)
        self.grok_options = QWidget()
        aspect_row = QHBoxLayout(self.grok_options)
        aspect_row.setContentsMargins(0, 0, 0, 0)
        aspect_row.addWidget(QLabel("Khung hình:"))
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(ASPECT_RATIOS)
        aspect_row.addWidget(self.aspect_combo, 1)
        preparation_layout.addWidget(self.grok_options)
        self.asset_options_toggle = QPushButton("Tùy chỉnh mô tả và loại ảnh")
        self.asset_options_toggle.setObjectName("linkButton")
        self.asset_options_toggle.setCheckable(True)
        preparation_layout.addWidget(self.asset_options_toggle)
        self.asset_options = QWidget()
        asset_options_layout = QVBoxLayout(self.asset_options)
        asset_options_layout.setContentsMargins(0, 0, 0, 0)
        self.asset_prompt_input = QTextEdit()
        self.asset_prompt_input.setPlaceholderText("Để trống để tạo ảnh theo bối cảnh ở trên.")
        self.asset_prompt_input.setFixedHeight(75)
        asset_options_layout.addWidget(self.asset_prompt_input)
        self.asset_role_combo = QComboBox()
        self.asset_role_combo.addItem("Ảnh khởi đầu / toàn cảnh", "start")
        self.asset_role_combo.addItem("Vật liệu tham chiếu", "reference")
        asset_options_layout.addWidget(self.asset_role_combo)
        preparation_layout.addWidget(self.asset_options)
        self.asset_options.hide()
        self.asset_options_toggle.toggled.connect(self.asset_options.setVisible)
        sample_row = QHBoxLayout()
        self.attach_sample_btn = QPushButton("Đính kèm hình mẫu để tạo ảnh")
        self.attach_sample_btn.setObjectName("linkButton")
        self.attach_sample_btn.clicked.connect(self._on_attach_asset_sample)
        sample_row.addWidget(self.attach_sample_btn)
        self.sample_label = QLabel("Tùy chọn")
        self.sample_label.setWordWrap(True)
        self.sample_label.setObjectName("mutedHint")
        sample_row.addWidget(self.sample_label, 1)
        self.open_sample_btn = QPushButton("Xem")
        self.open_sample_btn.setObjectName("linkButton")
        self.open_sample_btn.clicked.connect(self._on_open_asset_sample)
        self.open_sample_btn.hide()
        sample_row.addWidget(self.open_sample_btn)
        self.clear_sample_btn = QPushButton("Bỏ mẫu")
        self.clear_sample_btn.setObjectName("linkButton")
        self.clear_sample_btn.clicked.connect(self._on_clear_asset_sample)
        self.clear_sample_btn.hide()
        sample_row.addWidget(self.clear_sample_btn)
        preparation_layout.addLayout(sample_row)
        face_row = QHBoxLayout()
        self.attach_face_btn = QPushButton("Đính kèm khuôn mặt tham chiếu")
        self.attach_face_btn.setObjectName("linkButton")
        self.attach_face_btn.clicked.connect(self._on_attach_asset_face)
        face_row.addWidget(self.attach_face_btn)
        self.face_label = QLabel("Tùy chọn · ảnh chân dung rõ mặt")
        self.face_label.setWordWrap(True)
        self.face_label.setObjectName("mutedHint")
        face_row.addWidget(self.face_label, 1)
        self.open_face_btn = QPushButton("Xem")
        self.open_face_btn.setObjectName("linkButton")
        self.open_face_btn.clicked.connect(self._on_open_asset_face)
        self.open_face_btn.hide()
        face_row.addWidget(self.open_face_btn)
        self.clear_face_btn = QPushButton("Bỏ mặt")
        self.clear_face_btn.setObjectName("linkButton")
        self.clear_face_btn.clicked.connect(self._on_clear_asset_face)
        self.clear_face_btn.hide()
        face_row.addWidget(self.clear_face_btn)
        preparation_layout.addLayout(face_row)
        product_row = QHBoxLayout()
        self.attach_product_btn = QPushButton("Đính kèm ảnh sản phẩm chính")
        self.attach_product_btn.setObjectName("linkButton")
        self.attach_product_btn.clicked.connect(self._on_attach_product)
        product_row.addWidget(self.attach_product_btn)
        self.product_label = QLabel("Tùy chọn · chỉ dùng để tạo ảnh vật liệu")
        self.product_label.setWordWrap(True)
        self.product_label.setObjectName("mutedHint")
        product_row.addWidget(self.product_label, 1)
        self.clear_product_btn = QPushButton("Bỏ ảnh")
        self.clear_product_btn.setObjectName("linkButton")
        self.clear_product_btn.clicked.connect(self._on_clear_product)
        self.clear_product_btn.hide()
        product_row.addWidget(self.clear_product_btn)
        preparation_layout.addLayout(product_row)
        self.generate_asset_btn = QPushButton("Tạo ảnh khởi đầu với OpenAI")
        self.generate_asset_btn.setObjectName("primaryButton")
        self.generate_asset_btn.clicked.connect(self._on_generate_asset)
        preparation_layout.addWidget(self.generate_asset_btn)
        image_row = QHBoxLayout()
        self.attach_image_btn = QPushButton("Chọn ảnh có sẵn")
        self.attach_image_btn.setObjectName("linkButton")
        self.attach_image_btn.clicked.connect(self._on_attach_image)
        image_row.addWidget(self.attach_image_btn)
        self.reference_image_label = QLabel("Chưa có ảnh khởi đầu.")
        self.reference_image_label.setWordWrap(True)
        self.reference_image_label.setObjectName("mutedHint")
        image_row.addWidget(self.reference_image_label, 1)
        self.clear_image_btn = QPushButton("Bỏ ảnh")
        self.clear_image_btn.setObjectName("linkButton")
        self.clear_image_btn.setEnabled(False)
        self.clear_image_btn.clicked.connect(self._on_clear_reference_image)
        image_row.addWidget(self.clear_image_btn)
        preparation_layout.addLayout(image_row)
        self.add_material_btn = QPushButton("+ Thêm ảnh tham chiếu (nhân vật, sản phẩm…)")
        self.add_material_btn.setObjectName("linkButton")
        self.add_material_btn.clicked.connect(self._on_add_materials)
        preparation_layout.addWidget(self.add_material_btn)
        self.materials_hint_label = QLabel("Ảnh tham chiếu là tùy chọn, tối đa 4 ảnh.")
        self.materials_hint_label.setObjectName("mutedHint")
        preparation_layout.addWidget(self.materials_hint_label)
        self.materials_strip = QWidget()
        self.materials_strip_layout = QHBoxLayout(self.materials_strip)
        self.materials_strip_layout.setContentsMargins(0, 0, 0, 0)
        self.materials_strip_layout.addStretch(1)
        preparation_layout.addWidget(self.materials_strip)
        preparation_layout.addStretch(1)
        self.material_readiness = QLabel()
        self.material_readiness.setWordWrap(True)
        self.material_readiness.setObjectName("mutedHint")
        preparation_layout.addWidget(self.material_readiness)
        prepare_navigation = QHBoxLayout()
        self.next_step_btn = QPushButton("Tiếp tục → Viết kịch bản")
        self.next_step_btn.setObjectName("primaryButton")
        self.next_step_btn.clicked.connect(self._on_next_step)
        prepare_navigation.addWidget(self.next_step_btn, 1)
        preparation_layout.addLayout(prepare_navigation)

        render_layout.addWidget(QLabel("Kịch bản và bối cảnh sẽ dùng để dựng video"))
        self.script_review = QTextEdit()
        self.script_review.setReadOnly(True)
        self.script_review.setMinimumHeight(120)
        render_layout.addWidget(self.script_review, 1)
        self.material_summary = QLabel()
        self.material_summary.setWordWrap(True)
        render_layout.addWidget(self.material_summary)
        render_settings = QHBoxLayout()
        render_settings.addWidget(QLabel("Độ phân giải:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(RESOLUTIONS)
        render_settings.addWidget(self.resolution_combo, 1)
        render_settings.addWidget(QLabel("Thời lượng (giây):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 15)
        self.duration_spin.setValue(6)
        render_settings.addWidget(self.duration_spin)
        render_layout.addLayout(render_settings)
        self.back_step_btn = QPushButton("← Quay lại chỉnh kịch bản")
        self.back_step_btn.setObjectName("linkButton")
        self.back_step_btn.clicked.connect(lambda: self._go_to_step(1))
        render_layout.addWidget(self.back_step_btn)

        self.validation_hint = QLabel()
        self.validation_hint.setWordWrap(True)
        self.validation_hint.setObjectName("mutedHint")
        editor.addWidget(self.validation_hint)
        generate_row = QHBoxLayout()
        self.generate_btn = QPushButton("Tạo video với HeyGen")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.clicked.connect(self._on_generate)
        generate_row.addWidget(self.generate_btn, 1)
        self.stop_btn = QPushButton("Dừng tạo")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_generate)
        generate_row.addWidget(self.stop_btn)
        editor.addLayout(generate_row)

        self.preview_stack = QStackedWidget()
        self.preview_stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview_stack.setMinimumHeight(150)
        self.guide = QLabel("Chuẩn bị theo từng bước\n\n1. Tạo hoặc chọn ảnh để xác định nhân vật và bối cảnh.\n\n2. Viết kịch bản dựa trên vật liệu đã chuẩn bị.\n\n3. Kiểm tra nội dung rồi tạo video.")
        self.guide.setWordWrap(True)
        self.guide.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.preview_stack.addWidget(self.guide)
        self.asset_preview = MediaPreview("Ảnh sẽ xuất hiện ở đây sau khi bạn tạo hoặc đính kèm.")
        self.preview_stack.addWidget(self.asset_preview)
        self.preview = MediaPreview("Chưa có video. Chọn Avatar để xem trước.")
        self.preview_stack.addWidget(self.preview)
        preview_body.addWidget(self.preview_stack, 1)
        self.preview_asset_selector = QComboBox()
        self.preview_asset_selector.currentIndexChanged.connect(self._on_preview_asset_selected)
        preview_body.addWidget(self.preview_asset_selector)
        self.open_asset_btn = QPushButton("Mở ảnh vật liệu")
        self.open_asset_btn.setObjectName("linkButton")
        self.open_asset_btn.setEnabled(False)
        self.open_asset_btn.clicked.connect(self._on_open_asset)
        preview_body.addWidget(self.open_asset_btn)
        self.asset_edit_panel = QWidget()
        edit_layout = QVBoxLayout(self.asset_edit_panel)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        self.visual_editor_btn = QPushButton("Mở trình chỉnh sửa ảnh · Chọn vùng")
        self.visual_editor_btn.setObjectName("primaryButton")
        self.visual_editor_btn.clicked.connect(self._on_open_visual_editor)
        edit_layout.addWidget(self.visual_editor_btn)
        edit_layout.addWidget(QLabel("Chỉnh ảnh đang chọn bằng mô tả"))
        self.asset_edit_input = QTextEdit()
        self.asset_edit_input.setFixedHeight(75)
        self.asset_edit_input.setPlaceholderText("VD: Giữ khuôn mặt, đổi áo thành màu trắng và thêm ánh sáng ấm.")
        edit_layout.addWidget(self.asset_edit_input)
        self.edit_asset_btn = QPushButton("Áp dụng chỉnh sửa")
        self.edit_asset_btn.setObjectName("primaryButton")
        self.edit_asset_btn.clicked.connect(self._on_edit_asset)
        edit_layout.addWidget(self.edit_asset_btn)
        self.asset_version_combo = QComboBox()
        self.asset_version_combo.setToolTip("Chọn phiên bản để dùng làm vật liệu và tiếp tục chỉnh sửa")
        self.asset_version_combo.currentIndexChanged.connect(self._on_asset_version_selected)
        edit_layout.addWidget(self.asset_version_combo)
        preview_body.addWidget(self.asset_edit_panel)
        self.status_caption = QLabel("")
        self.status_caption.setObjectName("mutedHint")
        self.status_caption.setWordWrap(True)
        preview_body.addWidget(self.status_caption)
        self.open_btn = QPushButton("Mở video")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._on_open_video)
        self.to_post_btn = QPushButton("→ Dùng cho tab Đăng Facebook")
        self.to_post_btn.setObjectName("linkButton")
        self.to_post_btn.setEnabled(False)
        self.to_post_btn.clicked.connect(self._on_use_for_post)
        preview_body.addWidget(self.open_btn)
        preview_body.addWidget(self.to_post_btn)

        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self.workflow_stack.currentChanged.connect(self._refresh_workflow)
        self.script_input.textChanged.connect(self._refresh_workflow)
        self.video_prompt_input.textChanged.connect(self._refresh_workflow)
        self.asset_role_combo.currentIndexChanged.connect(self._refresh_workflow)
        self.asset_edit_input.textChanged.connect(self._refresh_asset_edit_controls)
        self._load_provider_setting()
        self._on_provider_changed()

    def set_context_from_content(self, content_text: str) -> None:
        self._content_context = content_text
        if not self._reference_busy and not self._asset_busy and self._cancel_event is None:
            self.script_input.setPlainText(content_text)
        self.log_message.emit("Đã nhận content để sử dụng cho video.", "info")

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
        if self._workflow_busy:
            self.log_message.emit("Chờ tác vụ hiện tại hoàn tất trước khi đổi ảnh vật liệu.", "info")
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.log_message.emit(f"Không đọc được ảnh: {path}", "error")
            return
        self._reference_image_path = path
        self._selected_asset_path = path
        self.reference_image_label.setText(f"Vật liệu: {path.name}")
        self.clear_image_btn.setEnabled(True)
        self.asset_preview.setPixmap(pixmap)
        self._refresh_workflow()
        self.log_message.emit(f"Đã đính kèm ảnh vật liệu cho Grok: {path.name}", "info")

    def _on_clear_reference_image(self) -> None:
        self._reference_image_path = None
        self.reference_image_label.setText("Chưa có ảnh khởi đầu. Tạo ảnh mới hoặc chọn ảnh có sẵn.")
        self.clear_image_btn.setEnabled(False)
        self._refresh_workflow()

    def _on_add_materials(self) -> None:
        paths_str, _ = QFileDialog.getOpenFileNames(self, "Chọn ảnh vật liệu tham chiếu", "", IMAGE_FILE_FILTER)
        if not paths_str:
            return
        room_left = MAX_REFERENCE_IMAGES - len(self._video_reference_paths())
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
        self._refresh_workflow()

    def _refresh_workflow(self) -> None:
        is_grok = self._current_provider() == PROVIDER_GROK
        step = self.workflow_stack.currentIndex()
        self.step_indicator.setVisible(is_grok)
        self.script_next_btn.setVisible(is_grok)
        self.back_material_btn.setVisible(is_grok)
        self.script_material_context.setVisible(is_grok)
        self.generate_btn.setVisible(not is_grok or step == 2)
        self.stop_btn.setVisible(self._cancel_event is not None)
        self.validation_hint.setVisible(bool(self.validation_hint.text()))
        for index, (label, title) in enumerate(zip(self.step_labels, ("Vật liệu", "Kịch bản", "Tạo video"))):
            label.setText(f"{'✓' if index < step else index + 1}  {title}")
            label.setStyleSheet(
                "background: #203d60; color: #ffffff; border-radius: 8px; font-weight: 600;"
                if index == step else "background: transparent; color: #8d9baa;"
            )
        self.editor_title.setText(("1 · Chuẩn bị vật liệu", "2 · Viết kịch bản", "3 · Kiểm tra và tạo video")[step]
                                  if is_grok else "Kịch bản & avatar")
        paths = ([self._reference_image_path] if self._reference_image_path else []) + self._material_image_paths
        names = ([f"Ảnh khởi đầu: {self._reference_image_path.name}"] if self._reference_image_path else [])
        names += [f"Tham chiếu {i + 1}: {path.name}" for i, path in enumerate(self._material_image_paths)]
        self.material_summary.setText(
            f"Khung hình {self.aspect_combo.currentText()} · {len(paths)} ảnh đính kèm\n" + "\n".join(names)
        )
        script = self.script_input.toPlainText().strip()
        scene = self.scene_input.toPlainText().strip()
        self.script_material_context.setText(
            f"Đã chuẩn bị {len(paths)} ảnh ở bước 1." + (f"\nBối cảnh: {scene}" if scene else "")
        )
        directions = self.video_prompt_input.toPlainText().strip()
        if not is_grok:
            self.generate_btn.setText("Tạo video với HeyGen Video Agent" if directions else "Tạo video với HeyGen")
        self.video_prompt_hint.setText(
            "Prompt sẽ dùng cùng kịch bản và ảnh vật liệu để dựng video Grok."
            if is_grok else "Có prompt: dùng HeyGen Video Agent với avatar/voice đã chọn. Để trống: avatar đọc kịch bản trực tiếp."
        )
        self.script_review.setPlainText((compose_video_prompt(directions, script) if directions else script)
                                       + (f"\n\nBối cảnh: {scene}" if scene else ""))
        self.script_next_btn.setEnabled(bool(script) and not self._workflow_busy)
        self.next_step_btn.setEnabled(bool(paths) and not self._workflow_busy)
        self.material_readiness.setText(
            f"Đã có {len(paths)} ảnh. Kiểm tra ảnh bên phải trước khi tiếp tục."
            if paths else "Tạo hoặc chọn ít nhất một ảnh để tiếp tục."
        )
        self.generate_asset_btn.setText(
            "Tạo ảnh tham chiếu với OpenAI" if self.asset_role_combo.currentData() == "reference"
            else ("Tạo lại ảnh khởi đầu" if self._reference_image_path else "Tạo ảnh khởi đầu với OpenAI")
        )
        self.clear_image_btn.setVisible(self._reference_image_path is not None)
        self.materials_strip.setVisible(bool(self._material_image_paths))
        if self._selected_asset_path not in paths:
            self._selected_asset_path = paths[0] if paths else None
        self.preview_asset_selector.blockSignals(True)
        self.preview_asset_selector.clear()
        for name, path in zip(names, paths):
            self.preview_asset_selector.addItem(name, path)
        if self._selected_asset_path:
            self.preview_asset_selector.setCurrentIndex(paths.index(self._selected_asset_path))
        self.preview_asset_selector.blockSignals(False)
        self._on_preview_asset_selected()
        show_video = not is_grok or (step == 2 and self._show_video_result)
        self.preview_stack.setCurrentIndex(2 if show_video else 1)
        self.preview_title.setText("Video của bạn" if show_video else ("Vật liệu để viết kịch bản" if step == 1 else "Xem trước vật liệu"))
        self.preview_asset_selector.setVisible(is_grok and not show_video and len(paths) > 1)
        self.open_asset_btn.setVisible(is_grok and not show_video)
        self.asset_edit_panel.setVisible(is_grok and step == 0 and bool(paths))
        self.preview_asset_selector.setEnabled(not self._workflow_busy)
        self.open_btn.setVisible(show_video and self._current_video_path is not None)
        self.to_post_btn.setVisible(show_video and self._current_video_path is not None)

    def _on_preview_asset_selected(self) -> None:
        path = self.preview_asset_selector.currentData()
        self.open_asset_btn.setEnabled(path is not None and path.is_file())
        if path:
            self._selected_asset_path = path
            self.asset_preview.setPixmap(QPixmap(str(path)))
        else:
            self.asset_preview.setText("Tạo ảnh hoặc chọn ảnh có sẵn.\nẢnh được chọn sẽ hiển thị lớn tại đây.")
        self._refresh_asset_edit_controls()

    def _refresh_asset_edit_controls(self) -> None:
        path = self.preview_asset_selector.currentData()
        enabled = path is not None and path.is_file() and not self._workflow_busy
        self.visual_editor_btn.setEnabled(enabled)
        self.asset_edit_input.setReadOnly(not enabled)
        self.edit_asset_btn.setEnabled(enabled and bool(self.asset_edit_input.toPlainText().strip()))
        self.asset_version_combo.blockSignals(True)
        self.asset_version_combo.clear()
        versions = self._asset_versions.get(path, [(path, "Ảnh ban đầu")] if path else [])
        for index, (version_path, description) in enumerate(versions):
            self.asset_version_combo.addItem(f"Phiên bản {index + 1} · {description[:70]}", version_path)
            self.asset_version_combo.setItemData(index, description, Qt.ItemDataRole.ToolTipRole)
            if version_path == path:
                self.asset_version_combo.setCurrentIndex(index)
        self.asset_version_combo.blockSignals(False)
        self.asset_version_combo.setVisible(len(versions) > 1)
        self.asset_version_combo.setEnabled(enabled)

    def _selected_asset_slot(self) -> int:
        # -1 denotes the starting frame; other values index the reference list.
        return self.preview_asset_selector.currentIndex() - (1 if self._reference_image_path else 0)

    def _replace_asset(self, slot: int, path: Path) -> None:
        if slot == -1:
            self._reference_image_path = path
            self.reference_image_label.setText(f"Vật liệu: {path.name}")
        else:
            self._material_image_paths[slot] = path
        self._selected_asset_path = path
        self._refresh_materials_strip()

    def _on_asset_version_selected(self) -> None:
        if self._workflow_busy:
            return
        path = self.asset_version_combo.currentData()
        if path is None:
            return
        if not path.is_file() or QPixmap(str(path)).isNull():
            self._show_validation("Không đọc được phiên bản ảnh này. Hãy chọn phiên bản khác.")
            self._refresh_asset_edit_controls()
            return
        self._replace_asset(self._selected_asset_slot(), path)
        self.status_caption.setText("Đã chọn phiên bản ảnh để dùng cho video.")

    def _on_open_visual_editor(self) -> None:
        if self._workflow_busy or (self._worker and self._worker.isRunning()):
            return
        path = self.preview_asset_selector.currentData()
        if path is None or QPixmap(str(path)).isNull():
            self._show_validation("Hãy chọn ảnh vật liệu hợp lệ để chỉnh sửa.")
            return
        slot = self._selected_asset_slot()
        dialog = ImageEditorDialog(path, self._asset_versions.get(path), self._asset_face_path, self)
        result = dialog.exec()
        for version_path, _ in dialog.versions:
            self._asset_versions[version_path] = dialog.versions
        if result == QDialog.DialogCode.Accepted:
            self._replace_asset(slot, dialog.current_path)
            self.status_caption.setText("Đã dùng ảnh từ trình chỉnh sửa làm vật liệu video.")
        else:
            self._refresh_asset_edit_controls()
        dialog.deleteLater()

    def _on_edit_asset(self) -> None:
        if self._workflow_busy or (self._worker and self._worker.isRunning()):
            return
        path = self.preview_asset_selector.currentData()
        instruction = self.asset_edit_input.toPlainText().strip()
        if path is None or not instruction:
            self._show_validation("Chọn ảnh vật liệu và nhập yêu cầu chỉnh sửa.")
            return
        face = self._asset_face_path
        try:
            for source in (path, face):
                if source is not None:
                    ImageClient.validate_reference_image(source)
                    if QPixmap(str(source)).isNull():
                        raise ValueError("Không đọc được ảnh đầu vào. Hãy chọn lại ảnh.")
            client = ImageClient(config.get_secret("openai_api_key"), config.load_settings()["openai_image_model"])
        except (ValueError, OSError) as exc:
            self._show_validation(str(exc))
            return
        image_number = 2 if face else 1
        prompt = (
            f"Chỉnh sửa ảnh {image_number} theo yêu cầu bên dưới. Giữ nguyên các chi tiết, bố cục "
            f"và phong cách không được yêu cầu thay đổi.\nYêu cầu chỉnh sửa: {instruction}"
        )
        if face:
            prompt += "\nẢnh 1 là khuôn mặt tham chiếu. Giữ đặc điểm nhận diện khuôn mặt này cho nhân vật chính."
        slot = self._selected_asset_slot()
        if self._workflow_busy:
            self.log_message.emit("Chờ tác vụ hiện tại hoàn tất trước khi đổi ảnh vật liệu.", "info")
            return
        pixmap = QPixmap(str(path))
        size = "1024x1024" if pixmap.width() == pixmap.height() else (
            "1536x1024" if pixmap.width() > pixmap.height() else "1024x1536"
        )
        self._asset_busy = True
        self._set_workflow_busy(True)
        self.status_caption.setText("Đang chỉnh sửa ảnh vật liệu…")
        self._worker = Worker(client.generate_image, prompt=prompt, size=size,
                              dest_dir=config.output_dir("images"), reference_image_path=path, face_image_path=face)
        self._worker.finished.connect(lambda result: self._on_asset_edit_done(slot, path, instruction, prompt, result))
        self._worker.error.connect(self._on_asset_error)
        self.processing_dialog.track(self._worker, "Đang chỉnh sửa ảnh vật liệu…")
        self._worker.start()

    def _on_asset_edit_done(self, slot: int, source: Path, instruction: str, prompt: str, path: Path) -> None:
        self._asset_busy = False
        if QPixmap(str(path)).isNull():
            self._on_asset_error("Không đọc được ảnh vừa chỉnh sửa. Ảnh trước vẫn được giữ nguyên.")
            return
        versions = self._asset_versions.setdefault(source, [(source, "Ảnh ban đầu")])
        versions.append((path, instruction))
        self._asset_versions[path] = versions
        self._replace_asset(slot, path)
        self.asset_edit_input.clear()
        self._set_workflow_busy(False)
        history_store.add_image(prompt, str(path))
        self.status_caption.setText("Đã áp dụng chỉnh sửa. Có thể sửa tiếp hoặc chọn lại phiên bản trước.")
        self.log_message.emit(f"Đã chỉnh sửa vật liệu: {path.name}", "success")

    def _on_open_asset(self) -> None:
        path = self.preview_asset_selector.currentData()
        if path is None or not path.is_file():
            self.open_asset_btn.setEnabled(False)
            self.log_message.emit("Không tìm thấy ảnh vật liệu. Hãy chọn lại ảnh.", "error")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            self.log_message.emit("Không thể mở ảnh. Hãy kiểm tra trình xem ảnh mặc định trên máy.", "error")

    def _show_validation(self, message: str) -> None:
        self.validation_hint.setText(message)
        self.validation_hint.show()
        self.log_message.emit(message, "error")

    def _go_to_step(self, step: int) -> None:
        if self._workflow_busy:
            return
        if step > self.workflow_stack.currentIndex() + 1:
            return
        if step > self.workflow_stack.currentIndex():
            if not self._validate_materials():
                return
            if step == 2 and not self.script_input.toPlainText().strip():
                self._show_validation("Vui lòng viết kịch bản ở bước 2 trước khi tạo video.")
                return
        self._show_video_result = False
        self.status_caption.clear()
        self.validation_hint.clear()
        self.workflow_stack.setCurrentIndex(step)
        self._refresh_workflow()

    def _on_script_next(self) -> None:
        if not self.script_input.toPlainText().strip():
            self._show_validation("Nhập kịch bản dựa trên vật liệu đã chuẩn bị trước khi tạo video.")
            return
        if self._validate_materials():
            self._go_to_step(2)

    def _validate_materials(self) -> bool:
        if len(self._video_reference_paths()) > MAX_REFERENCE_IMAGES:
            self._show_validation(f"Tối đa {MAX_REFERENCE_IMAGES} ảnh vật liệu tham chiếu. Hãy bỏ bớt ảnh.")
            return False
        paths = ([self._reference_image_path] if self._reference_image_path else []) + self._material_image_paths
        if not paths:
            self._show_validation("Hãy tạo hoặc đính kèm ảnh ở phần Vật liệu trước khi tạo video.")
            return False
        if any(not path.is_file() or QPixmap(str(path)).isNull() for path in paths):
            self._show_validation("Có ảnh vật liệu không còn đọc được. Hãy chọn lại ảnh ở phần Vật liệu.")
            return False
        return True

    def _on_next_step(self) -> None:
        if self._validate_materials():
            self._go_to_step(1)

    def _set_workflow_busy(self, busy: bool) -> None:
        self._workflow_busy = busy
        self.provider_combo.setEnabled(not busy)
        self.workflow_stack.setEnabled(not busy)
        self.script_input.setReadOnly(busy)
        self.reference_video_btn.setEnabled(not busy)
        self.analyze_reference_btn.setEnabled(not busy and self._reference_video_path is not None)
        self.generate_btn.setEnabled(not busy)
        self._refresh_workflow()

    def _on_generate_asset(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        scene = self.scene_input.toPlainText().strip()
        description = self.asset_prompt_input.toPlainText().strip()
        if not (scene or description):
            self._show_validation("Nhập bối cảnh hoặc mô tả ảnh trước khi tạo vật liệu.")
            return
        for input_path in (self._asset_face_path, self._asset_sample_path, self._product_image_path):
            if input_path is None:
                continue
            try:
                ImageClient.validate_reference_image(input_path)
                if QPixmap(str(input_path)).isNull():
                    raise ValueError("Không đọc được hình mẫu. Hãy chọn lại ảnh.")
            except (ValueError, OSError) as exc:
                self._show_validation(str(exc))
                return
        role = self.asset_role_combo.currentData()
        if role == "reference" and len(self._video_reference_paths()) >= MAX_REFERENCE_IMAGES:
            self.log_message.emit(f"Chỉ được đính kèm tối đa {MAX_REFERENCE_IMAGES} ảnh tham chiếu.", "error")
            return
        try:
            settings = config.load_settings()
            client = ImageClient(config.get_secret("openai_api_key"), settings["openai_image_model"])
        except ValueError as exc:
            self.log_message.emit(str(exc), "error")
            return
        purpose = "khung hình mở đầu hoàn chỉnh" if role == "start" else "ảnh vật liệu tham chiếu"
        prompt = (
            f"Tạo {purpose} để dựng video. Không thêm chữ hoặc chia ô storyboard.\n"
            f"Bối cảnh và tính nhất quán: {scene}\nYêu cầu ảnh: {description}"
        )
        if self._asset_face_path is not None:
            prompt += "\nẢnh 1 là khuôn mặt tham chiếu: dùng khuôn mặt này cho nhân vật chính, giữ các đặc điểm nhận diện, đường nét và tỷ lệ khuôn mặt; điều chỉnh tư thế, trang phục và ánh sáng theo yêu cầu."
        if self._asset_sample_path is not None:
            sample_number = 2 if self._asset_face_path is not None else 1
            prompt += f"\nẢnh {sample_number} là hình mẫu bối cảnh và phong cách; điều chỉnh theo mô tả ở trên."
            if self._asset_face_path is not None:
                prompt += " Ưu tiên khuôn mặt trong ảnh 1, không dùng khuôn mặt của người trong hình mẫu bối cảnh."
        if self._product_image_path:
            product_number = 1 + int(self._asset_face_path is not None) + int(self._asset_sample_path is not None)
            prompt += f"\nẢnh {product_number} là sản phẩm chính: đưa sản phẩm này vào bối cảnh, giữ nguyên hình dáng, màu sắc, logo, nhãn và bao bì; không thay bằng sản phẩm khác."
        width, height = map(int, self.aspect_combo.currentText().split(":"))
        size = "1024x1024" if width == height else ("1536x1024" if width > height else "1024x1536")
        self._asset_busy = True
        self._set_workflow_busy(True)
        self.status_caption.setText("Đang tạo ảnh vật liệu…")
        self._worker = Worker(
            client.generate_image, prompt=prompt, size=size, dest_dir=config.output_dir("images"),
            reference_image_path=self._asset_sample_path,
            face_image_path=self._asset_face_path,
            product_image_path=self._product_image_path,
        )
        self._worker.finished.connect(lambda path: self._on_asset_done(prompt, role, path))
        self._worker.error.connect(self._on_asset_error)
        self.processing_dialog.track(self._worker, "Đang tạo ảnh vật liệu…")
        self._worker.start()

    def _on_attach_asset_sample(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Chọn hình mẫu để tạo vật liệu", "", IMAGE_FILE_FILTER)
        if not path_str:
            return
        path = Path(path_str)
        try:
            ImageClient.validate_reference_image(path)
            if QPixmap(str(path)).isNull():
                raise ValueError("Không đọc được hình mẫu. Hãy chọn ảnh khác.")
        except (ValueError, OSError) as exc:
            self._show_validation(str(exc))
            return
        self._asset_sample_path = path
        self.sample_label.setText(path.name)
        self.sample_label.setToolTip(str(path))
        self.open_sample_btn.show()
        self.clear_sample_btn.show()
        self.attach_sample_btn.setText("Đổi hình mẫu")

    def _on_clear_asset_sample(self) -> None:
        self._asset_sample_path = None
        self.sample_label.setText("Tùy chọn")
        self.sample_label.setToolTip("")
        self.open_sample_btn.hide()
        self.clear_sample_btn.hide()
        self.attach_sample_btn.setText("Đính kèm hình mẫu để tạo ảnh")

    def _on_open_asset_sample(self) -> None:
        path = self._asset_sample_path
        if path is None or not path.is_file():
            self._show_validation("Không tìm thấy hình mẫu. Hãy chọn lại ảnh.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            self.log_message.emit("Không thể mở hình mẫu. Hãy kiểm tra trình xem ảnh mặc định.", "error")

    def _video_reference_paths(self) -> list[Path]:
        # Raw product/face/scene sources belong only to image generation.
        return list(self._material_image_paths)

    def _on_attach_product(self) -> None:
        if self._workflow_busy:
            return
        path_str, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh sản phẩm chính", "", IMAGE_FILE_FILTER)
        if not path_str:
            return
        path = Path(path_str)
        try:
            ImageClient.validate_reference_image(path)
            if QPixmap(str(path)).isNull():
                raise ValueError("Không đọc được ảnh sản phẩm. Hãy chọn ảnh khác.")
        except (ValueError, OSError) as exc:
            self._show_validation(str(exc))
            return
        self._product_image_path = path
        self.product_label.setText(path.name)
        self.product_label.setToolTip(str(path))
        self.attach_product_btn.setText("Đổi ảnh sản phẩm chính")
        self.clear_product_btn.show()
        self._refresh_workflow()

    def _on_clear_product(self) -> None:
        if self._workflow_busy:
            return
        self._product_image_path = None
        self.product_label.setText("Tùy chọn · chỉ dùng để tạo ảnh vật liệu")
        self.product_label.setToolTip("")
        self.attach_product_btn.setText("Đính kèm ảnh sản phẩm chính")
        self.clear_product_btn.hide()
        self._refresh_workflow()

    def _on_attach_asset_face(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh khuôn mặt tham chiếu", "", IMAGE_FILE_FILTER)
        if not path_str:
            return
        path = Path(path_str)
        try:
            ImageClient.validate_reference_image(path)
            if QPixmap(str(path)).isNull():
                raise ValueError("Không đọc được ảnh khuôn mặt. Hãy chọn ảnh khác.")
        except (ValueError, OSError) as exc:
            self._show_validation(str(exc))
            return
        self._asset_face_path = path
        self.face_label.setText(path.name)
        self.face_label.setToolTip(str(path))
        self.open_face_btn.show()
        self.clear_face_btn.show()
        self.attach_face_btn.setText("Đổi ảnh khuôn mặt")

    def _on_clear_asset_face(self) -> None:
        self._asset_face_path = None
        self.face_label.setText("Tùy chọn · ảnh chân dung rõ mặt")
        self.face_label.setToolTip("")
        self.open_face_btn.hide()
        self.clear_face_btn.hide()
        self.attach_face_btn.setText("Đính kèm khuôn mặt tham chiếu")

    def _on_open_asset_face(self) -> None:
        path = self._asset_face_path
        if path is None or not path.is_file():
            self._show_validation("Không tìm thấy ảnh khuôn mặt. Hãy chọn lại ảnh.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            self.log_message.emit("Không thể mở ảnh khuôn mặt. Hãy kiểm tra trình xem ảnh mặc định.", "error")

    def _on_asset_done(self, prompt: str, role: str, path: Path) -> None:
        self._asset_busy = False
        self._set_workflow_busy(False)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._on_asset_error("Không đọc được ảnh vừa tạo. Hãy thử lại.")
            return
        if role == "start":
            self.set_reference_image(path)
        else:
            self._material_image_paths.append(path)
            self._selected_asset_path = path
            self._refresh_materials_strip()
        self.asset_preview.setPixmap(pixmap)
        history_store.add_image(prompt, str(path))
        self.status_caption.setText("Ảnh đã đính kèm. Kiểm tra ảnh rồi bấm Tiếp tục.")
        self.log_message.emit(f"Đã tạo và đính kèm vật liệu: {path.name}", "success")

    def _on_asset_error(self, message: str) -> None:
        self._asset_busy = False
        self._set_workflow_busy(False)
        self.status_caption.setText(f"Lỗi tạo vật liệu: {message}")
        self.log_message.emit(f"Lỗi tạo vật liệu: {message}", "error")

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
        self.workflow_stack.setCurrentIndex(1 if is_heygen else 0)

        if is_heygen:
            self.script_label.setText("Kịch bản (script) để avatar đọc:")
            self.script_input.setPlaceholderText("Nhập lời thoại cho video, hoặc phân tích video mẫu bên dưới.")
            self.generate_btn.setText("Tạo video với HeyGen")
            if not self._avatar_previews:
                self.preview.setText("Chưa có video. Chọn Avatar để xem trước.")
        else:
            self.script_label.setText("Nội dung và diễn biến của video")
            self.script_input.setPlaceholderText(
                "Dựa trên ảnh bên phải, mô tả diễn biến, hành động, lời thoại và chuyển động máy quay."
            )
            self.generate_btn.setText("Tạo video với Grok")
            self.preview.setText("Chưa có video. Nhập mô tả và bấm Tạo video.")

        settings = config.load_settings()
        settings["video_provider"] = provider
        config.save_settings(settings)
        self._refresh_workflow()

    def _on_load_avatars(self) -> None:
        client = self._make_heygen_client()
        if not client:
            return
        self.load_avatars_btn.setEnabled(False)
        self.log_message.emit("Đang tải My Avatar / My Voice từ HeyGen...", "info")
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
        self.log_message.emit(f"Đã tải {len(avatars)} My Avatar và {len(voices)} My Voice.", "success")
        if not avatars or not voices:
            self.log_message.emit("Chưa có đủ avatar/voice cá nhân. Kiểm tra My Avatar và My Voice trong tài khoản HeyGen.", "info")

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

    def _on_attach_reference_video(self) -> None:
        if self._reference_busy:
            return
        path_str, _ = QFileDialog.getOpenFileName(self, "Chọn video/audio mẫu", "", SAMPLE_FILE_FILTER)
        if not path_str:
            return
        path = Path(path_str)
        if not path.is_file():
            self.log_message.emit("Không tìm thấy tệp mẫu. Hãy chọn lại.", "error")
            return
        self._reference_video_path = path
        self.reference_video_label.setText(f"{path.name} · {path.stat().st_size / (1024 * 1024):.1f} MB · Sẵn sàng phân tích")
        self.reference_video_label.setToolTip(str(path))
        self.analyze_reference_btn.setEnabled(True)

    def _on_analyze_reference_video(self) -> None:
        if self._reference_busy or (self._worker and self._worker.isRunning()):
            self.log_message.emit("Chờ tác vụ video hiện tại hoàn tất trước khi phân tích mẫu.", "info")
            return
        if not self._reference_video_path or not self._reference_video_path.is_file():
            self.reference_video_label.setText("Hãy chọn video/audio mẫu hợp lệ trước khi phân tích.")
            self.analyze_reference_btn.setEnabled(False)
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

        self._set_reference_busy(True)
        self._on_reference_progress("Đang trích xuất âm thanh và phân tích lời thoại…")
        self._worker = Worker(
            self._build_script_from_reference,
            transcription_client=transcription_client,
            text_client=text_client,
            file_path=self._reference_video_path,
            content_text=self._content_context,
            target=self._current_provider(),
            duration=self.duration_spin.value(),
            aspect_ratio=self.aspect_combo.currentText(),
        )
        self._worker.progress.connect(self._on_reference_progress)
        self._worker.finished.connect(self._on_reference_script_done)
        self._worker.error.connect(self._on_reference_error)
        self._worker.start()

    def _set_reference_busy(self, busy: bool) -> None:
        self._reference_busy = busy
        self._set_workflow_busy(busy)
        self.analyze_reference_btn.setText("Đang phân tích…" if busy else "Phân tích")
        self.load_avatars_btn.setEnabled(not busy)

    def _on_reference_progress(self, message: str) -> None:
        self.reference_video_label.setText(message)
        self.log_message.emit(message, "info")

    def _on_reference_error(self, message: str) -> None:
        self._set_reference_busy(False)
        self.reference_video_label.setText(f"Phân tích chưa thành công: {message}")
        self.log_message.emit(f"Lỗi phân tích video mẫu: {message}", "error")

    @staticmethod
    def _build_script_from_reference(
        transcription_client: TranscriptionClient,
        text_client,
        file_path: Path,
        content_text: str,
        target: str = PROVIDER_HEYGEN,
        duration: int = 6,
        aspect_ratio: str = "16:9",
        on_progress=None,
    ) -> str:
        transcript = transcription_client.transcribe(file_path)
        if on_progress:
            on_progress("Đã có lời thoại, đang chuyển ý tưởng thành prompt…")
        result = text_client.suggest_video_script_from_reference(
            transcript, content_text, target=target, duration=duration, aspect_ratio=aspect_ratio
        )
        if not result or not result.strip():
            raise RuntimeError("Chưa nhận được ý tưởng. Hãy bấm Phân tích để thử lại.")
        return result.strip()

    def _on_reference_script_done(self, script: str) -> None:
        self.script_input.setPlainText(script)
        self._set_reference_busy(False)
        self.script_input.setFocus()
        self.reference_video_label.setText("Đã đưa ý tưởng vào prompt. Bạn có thể chỉnh sửa trước khi tạo video.")
        self.log_message.emit("Đã phân tích lời thoại video mẫu và điền ý tưởng vào prompt.", "success")

    def _video_prompt_source(self):
        is_grok = self._current_provider() == PROVIDER_GROK
        return (self.script_input.toPlainText().strip(), self._current_provider(),
                self.scene_input.toPlainText().strip() if is_grok else "",
                self.duration_spin.value() if is_grok else None,
                self.aspect_combo.currentText() if is_grok else None)

    def _on_create_video_prompt(self) -> None:
        if self._workflow_busy or (self._worker and self._worker.isRunning()):
            return
        source = self._video_prompt_source()
        if not source[0]:
            self._show_validation("Nhập kịch bản trước khi tạo prompt.")
            return
        try:
            client = get_text_client(config.load_settings().get("content_provider", PROVIDER_CLAUDE))
        except ValueError as exc:
            self._show_validation(str(exc))
            return
        self._set_workflow_busy(True)
        self.load_avatars_btn.setEnabled(False)
        self.status_caption.setText("Đang tạo prompt từ kịch bản…")
        self._worker = Worker(create_video_prompt, client, source[0], source[1], source[2],
                              source[3] or 6, source[4] or "16:9")
        self._worker.finished.connect(lambda prompt: self._on_video_prompt_done(source, prompt))
        self._worker.error.connect(self._on_video_prompt_error)
        self.processing_dialog.track(self._worker, "Đang tạo prompt từ kịch bản…")
        self._worker.start()

    def _on_video_prompt_done(self, source, prompt: str) -> None:
        self._prompt_source = source
        self.video_prompt_input.setPlainText(prompt)
        self._set_workflow_busy(False)
        self.load_avatars_btn.setEnabled(True)
        self.status_caption.setText("Đã tạo prompt. Kiểm tra và chỉnh sửa trước khi tạo video.")
        self.log_message.emit("Đã tạo prompt dựng video từ kịch bản.", "success")

    def _on_video_prompt_error(self, message: str) -> None:
        self._set_workflow_busy(False)
        self.load_avatars_btn.setEnabled(True)
        self.status_caption.setText(f"Không thể tạo prompt: {message}")
        self.log_message.emit(f"Lỗi tạo prompt: {message}", "error")

    def _on_generate(self) -> None:
        if self._reference_busy or (self._worker and self._worker.isRunning()):
            return
        if (self.video_prompt_input.toPlainText().strip() and self._prompt_source is not None
                and self._prompt_source != self._video_prompt_source()):
            self._show_validation("Kịch bản hoặc thiết lập đã đổi. Hãy tạo lại prompt, hoặc xoá prompt để dùng kịch bản trực tiếp.")
            return
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
        directions = self.video_prompt_input.toPlainText().strip()
        prompt_options = {"prompt": compose_video_prompt(directions, script)} if directions else {}
        self._worker = Worker(
            client.generate_from_prompt_and_wait if directions else client.generate_and_wait,
            avatar_id=avatar_id,
            voice_id=voice_id,
            script_text=script,
            dest_dir=config.output_dir("videos"),
            cancel_event=self._cancel_event,
            **prompt_options,
        )
        self._worker.progress.connect(lambda msg: self.status_caption.setText(msg))
        self._worker.thumbnail.connect(self._on_thumbnail_ready)
        self._worker.finished.connect(lambda path: self._on_done(prompt_options.get("prompt", script), path))
        self._worker.error.connect(self._on_error)
        self._worker.cancelled.connect(self._on_generate_cancelled)
        self.processing_dialog.track(self._worker, "Đang tạo video với HeyGen...")
        self._worker.start()

    def _on_generate_grok(self) -> None:
        if not self._validate_materials():
            self.workflow_stack.setCurrentIndex(0)
            return
        if not self.script_input.toPlainText().strip():
            self._show_validation("Vui lòng viết kịch bản ở bước 2 trước khi tạo video.")
            self.workflow_stack.setCurrentIndex(1)
            return
        if self.workflow_stack.currentIndex() != 2:
            self._show_validation("Bấm Tiếp tục để kiểm tra nội dung trước khi tạo video.")
            return
        prompt = self.script_input.toPlainText().strip()
        directions = self.video_prompt_input.toPlainText().strip()
        if directions:
            prompt = compose_video_prompt(directions, prompt)
        scene = self.scene_input.toPlainText().strip()
        if scene:
            prompt += f"\n\nBối cảnh và vật liệu cần giữ nhất quán:\n{scene}"
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
            reference_image_paths=self._video_reference_paths() or None,
            cancel_event=self._cancel_event,
        )
        self._worker.progress.connect(lambda msg: self.status_caption.setText(msg))
        self._worker.finished.connect(lambda path: self._on_done(prompt, path))
        self._worker.error.connect(self._on_error)
        self._worker.cancelled.connect(self._on_generate_cancelled)
        self.processing_dialog.track(self._worker, "Đang tạo video với Grok...")
        self._worker.start()

    def _start_generation(self, message: str) -> None:
        self._show_video_result = True
        self._set_workflow_busy(True)
        self.generate_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.open_btn.setEnabled(False)
        self.to_post_btn.setEnabled(False)
        self.log_message.emit(message, "info")
        self.status_caption.setText("Đang xử lý...")
        self._cancel_event = threading.Event()
        self.preview.setText(message)
        self._refresh_workflow()

    def _on_stop_generate(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        self.stop_btn.setEnabled(False)
        self.status_caption.setText("Đang huỷ...")
        self.log_message.emit("Đang huỷ tạo video (chờ vòng kiểm tra kế tiếp)...", "info")

    def _on_generate_cancelled(self) -> None:
        self._show_video_result = False
        self._set_workflow_busy(False)
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._cancel_event = None
        self.status_caption.setText("Đã huỷ tạo video.")
        self.preview.setText("Đã huỷ tạo video. Bạn có thể chỉnh nội dung và thử lại.")
        self._refresh_workflow()
        self.log_message.emit("Đã huỷ tạo video theo yêu cầu.", "info")

    def _on_thumbnail_ready(self, url: str) -> None:
        # A real frame from the video HeyGen is rendering — swap it in for the static
        # avatar photo so the preview tracks actual progress, not just a placeholder.
        self._load_preview_image(url, caption="Khung hình từ video đang tạo (HeyGen)")

    def _on_done(self, script: str, path: Path) -> None:
        self._show_video_result = True
        self._set_workflow_busy(False)
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._cancel_event = None
        self._current_video_path = path
        self.preview.setText("Video đã sẵn sàng. Bấm Mở video để xem kết quả.")
        self._refresh_workflow()
        self.status_caption.setText(f"Hoàn tất: {path}")
        self.open_btn.setEnabled(True)
        self.to_post_btn.setEnabled(True)
        history_store.add_video(script, str(path))
        self.video_generated.emit(path)
        self.log_message.emit(f"Đã tạo video: {path}", "success")

    def _on_open_video(self) -> None:
        if self._current_video_path:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._current_video_path.resolve()))):
                self.log_message.emit("Không thể mở video. Hãy kiểm tra trình phát video mặc định.", "error")

    def _on_use_for_post(self) -> None:
        if self._current_video_path:
            self.video_generated.emit(self._current_video_path)

    def _on_error(self, message: str) -> None:
        self._show_video_result = False
        self._set_workflow_busy(False)
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._cancel_event = None
        self.load_avatars_btn.setEnabled(True)
        self.reference_video_btn.setEnabled(True)
        self.status_caption.setText(f"Lỗi: {message}")
        self._refresh_workflow()
        self.log_message.emit(f"Lỗi tạo video: {message}", "error")
