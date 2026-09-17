"""View and edit the shared content system prompt with acknowledged DB saves."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.core.content_prompts import SYSTEM_PROMPT_POST, get_post_system_prompt, save_post_system_prompt
from app.workers.async_worker import Worker


class PostPromptEditor(QWidget):
    busy_changed = Signal(bool)
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._loaded = False
        self._original = ""
        self.busy = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.toggle_btn = QPushButton("Xem / sửa prompt chính")
        self.toggle_btn.setObjectName("linkButton")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._toggle)
        layout.addWidget(self.toggle_btn)
        self.panel = QWidget()
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(10)
        description = QLabel("Prompt chính định hướng cách AI viết content. Chủ đề, giọng điệu, độ dài và đối tượng đọc vẫn lấy từ các ô bên trên. Prompt đã lưu dùng chung cho Claude, OpenAI và quy trình tự động.")
        description.setWordWrap(True)
        panel_layout.addWidget(description)
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setAccessibleName("Prompt chính viết content")
        self.editor.setFixedHeight(220)
        self.editor.textChanged.connect(self._text_changed)
        panel_layout.addWidget(self.editor)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        panel_layout.addWidget(self.status_label)
        self.reload_btn = QPushButton("Tải lại từ DB")
        self.reset_btn = QPushButton("Dùng prompt mặc định")
        self.save_btn = QPushButton("Lưu prompt vào DB")
        self.save_btn.setObjectName("primaryButton")
        self.reload_btn.clicked.connect(self.reload)
        self.reset_btn.clicked.connect(self.reset)
        self.save_btn.clicked.connect(self.save)
        for button in (self.reload_btn, self.reset_btn, self.save_btn):
            panel_layout.addWidget(button)
        layout.addWidget(self.panel)
        self.panel.hide()

    @property
    def dirty(self):
        return self._loaded and self.editor.toPlainText().strip() != self._original

    def _toggle(self, checked):
        self.panel.setVisible(checked)
        if checked and not self._loaded and not self.busy:
            self.reload()

    def _set_busy(self, busy):
        self.busy = busy
        self.editor.setReadOnly(busy or not self._loaded)
        self.reload_btn.setEnabled(not busy)
        self.reset_btn.setEnabled(not busy and self._loaded)
        self.save_btn.setEnabled(not busy and self._loaded)
        self.busy_changed.emit(busy)

    def reload(self):
        if self.busy:
            return
        self._set_busy(True)
        self.status_label.setText("Đang tải prompt từ DB...")
        self._worker = Worker(get_post_system_prompt)
        self._worker.finished.connect(self._loaded_prompt)
        self._worker.error.connect(self._error)
        self._worker.start()

    def _loaded_prompt(self, text):
        self._original = text.strip()
        self._loaded = True
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
        self._set_busy(False)
        self.status_label.setText("Prompt đang dùng. Chỉnh sửa rồi lưu vào DB để áp dụng cho lần tạo tiếp theo.")

    def _text_changed(self):
        if not self.busy:
            self.status_label.setText("Có thay đổi chưa lưu. Nhấn Lưu prompt vào DB trước khi viết content." if self.dirty else "Prompt đang dùng.")

    def reset(self):
        if self.busy:
            return
        self.editor.setPlainText(SYSTEM_PROMPT_POST)
        self.status_label.setText("Đã nạp prompt mặc định. Nhấn Lưu prompt vào DB để áp dụng.")

    def save(self):
        if self.busy or not self._loaded:
            return
        text = self.editor.toPlainText().strip()
        if not text:
            self._error("Prompt không được để trống.")
            return
        self._set_busy(True)
        self.status_label.setText("Đang lưu prompt vào DB...")
        self._worker = Worker(save_post_system_prompt, text)
        self._worker.finished.connect(self._saved_prompt)
        self._worker.error.connect(self._error)
        self._worker.start()

    def _saved_prompt(self, text):
        self._loaded_prompt(text)
        self.status_label.setText("Đã lưu prompt vào DB. Các lần viết content tiếp theo sẽ dùng prompt này.")
        self.log_message.emit("Đã lưu prompt chính viết content vào DB.", "success")

    def _error(self, message):
        self._set_busy(False)
        self.status_label.setText(f"Lỗi prompt: {message}")
        self.log_message.emit(f"Lỗi prompt: {message}", "error")
