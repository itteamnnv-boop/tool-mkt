"""Tab: đăng video lên YouTube qua Data API v3 (resumable upload)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.youtube_client import CATEGORY_LABELS, PRIVACY_LABELS, VIDEO_FILE_FILTER, YouTubeClient
from app.storage import history_store
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.workers.async_worker import Worker


from app.core.social_tokens import ensure_youtube_token as _ensure_valid_token


class YouTubeTab(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_path: Path | None = None
        self._worker: Worker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(make_page_header("🎥 Đăng YouTube", "Tải video lên kênh YouTube của bạn qua Data API v3."))

        layout.addWidget(QLabel("Tiêu đề:"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Để trống sẽ dùng tên file video làm tiêu đề.")
        layout.addWidget(self.title_input)

        layout.addWidget(QLabel("Mô tả:"))
        self.description_input = QTextEdit()
        self.description_input.setFixedHeight(110)
        layout.addWidget(self.description_input)

        layout.addWidget(QLabel("Thẻ tag (phân cách bằng dấu phẩy):"))
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("VD: phân bón, nông nghiệp, hữu cơ")
        layout.addWidget(self.tags_input)

        media_row = QVBoxLayout()
        self.video_path_label = QLabel("(chưa chọn video)")
        self.video_path_label.setWordWrap(True)
        self.browse_btn = QPushButton("Chọn video...")
        self.browse_btn.clicked.connect(self._on_browse)
        media_row.addWidget(self.video_path_label, stretch=1)
        media_row.addWidget(self.browse_btn)
        layout.addLayout(media_row)

        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("Chuyên mục:"))
        self.category_combo = QComboBox()
        for value, label in CATEGORY_LABELS.items():
            self.category_combo.addItem(label, value)
        options_row.addWidget(self.category_combo)
        options_row.addWidget(QLabel("Quyền riêng tư:"))
        self.privacy_combo = QComboBox()
        for value, label in PRIVACY_LABELS.items():
            self.privacy_combo.addItem(label, value)
        options_row.addWidget(self.privacy_combo)
        layout.addLayout(options_row)

        self.post_btn = QPushButton("Đăng lên YouTube")
        self.post_btn.setObjectName("primaryButton")
        self.post_btn.clicked.connect(self._on_post)
        layout.addWidget(self.post_btn)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        arrange_cards(layout, [("Nội dung & vật liệu", [0, 1, 2, 3, 4, 5, 6, 7]), ("Xuất bản", [8, 9])])

    # ---------- Cross-tab wiring ----------

    def set_message(self, text: str) -> None:
        self.description_input.setPlainText(text)

    def set_video_path(self, path: Path) -> None:
        self._video_path = path
        self.video_path_label.setText(str(path))
        self.log_message.emit(f"Đã gắn video vào bài đăng YouTube: {path}", "info")

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn video", "", VIDEO_FILE_FILTER)
        if path:
            self._video_path = Path(path)
            self.video_path_label.setText(str(self._video_path))

    # ---------- Posting ----------

    def _on_post(self) -> None:
        if not self._video_path:
            self.log_message.emit("Chưa chọn video để đăng.", "error")
            return
        account = config.get_youtube_account()
        if not account.get("access_token"):
            self.log_message.emit("Chưa kết nối YouTube — vào tab 'Kết nối YouTube' trước.", "error")
            return

        privacy_level = self.privacy_combo.currentData()
        privacy_label = self.privacy_combo.currentText()
        confirm = QMessageBox.question(
            self,
            "Xác nhận đăng YouTube",
            f"Bạn sắp tải video lên kênh YouTube (quyền riêng tư: {privacy_label}). Tiếp tục?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        tags = [t.strip() for t in self.tags_input.text().split(",") if t.strip()]

        self.post_btn.setEnabled(False)
        self.status_label.setText("Đang chuẩn bị đăng...")
        self.log_message.emit("Đang tải video lên YouTube...", "info")
        self._worker = Worker(
            self._post_worker,
            video_path=self._video_path,
            title=self.title_input.text().strip(),
            description=self.description_input.toPlainText().strip(),
            tags=tags,
            category_id=self.category_combo.currentData(),
            privacy_status=privacy_level,
        )
        self._worker.progress.connect(lambda msg: self.status_label.setText(msg))
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @staticmethod
    def _post_worker(
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        category_id: str,
        privacy_status: str,
        on_progress=None,
    ) -> dict:
        access_token = _ensure_valid_token(on_progress=on_progress)
        client = YouTubeClient(access_token)
        return client.upload_video(
            video_path,
            title=title,
            description=description,
            tags=tags,
            category_id=category_id,
            privacy_status=privacy_status,
            on_progress=on_progress,
        )

    def _on_done(self, result: dict) -> None:
        self.post_btn.setEnabled(True)
        video_id = result.get("id", "")
        self.status_label.setText(
            f"Đã đăng lên YouTube thành công. Video ID: {video_id}" if video_id else "Đã đăng lên YouTube thành công."
        )
        history_store.add_post(
            "youtube_video",
            self.title_input.text().strip() or self.description_input.toPlainText().strip(),
            str(self._video_path or ""),
            facebook_post_id=video_id,
            ok=True,
        )
        self.log_message.emit("Đăng YouTube thành công.", "success")

    def _on_error(self, message: str) -> None:
        self.post_btn.setEnabled(True)
        self.status_label.setText("Đăng YouTube thất bại.")
        history_store.add_post(
            "youtube_video",
            self.title_input.text().strip() or self.description_input.toPlainText().strip(),
            str(self._video_path or ""),
            ok=False,
        )
        self.log_message.emit(f"Lỗi đăng YouTube: {message}", "error")
