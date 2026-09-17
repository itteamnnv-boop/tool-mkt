"""Tab: đăng video lên TikTok qua Content Posting API (Direct Post, chỉ hỗ trợ video)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.tiktok_client import PRIVACY_LABELS, VIDEO_FILE_FILTER, TikTokClient
from app.storage import history_store
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.workers.async_worker import Worker


from app.core.social_tokens import ensure_tiktok_token as _ensure_valid_token


class TikTokTab(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_path: Path | None = None
        self._worker: Worker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(make_page_header("🎵 Đăng TikTok", "Đăng video lên TikTok qua Content Posting API."))

        layout.addWidget(QLabel("Caption:"))
        self.caption_input = QTextEdit()
        self.caption_input.setFixedHeight(110)
        layout.addWidget(self.caption_input)

        media_row = QVBoxLayout()
        self.video_path_label = QLabel("(chưa chọn video)")
        self.video_path_label.setWordWrap(True)
        self.browse_btn = QPushButton("Chọn video...")
        self.browse_btn.clicked.connect(self._on_browse)
        media_row.addWidget(self.video_path_label, stretch=1)
        media_row.addWidget(self.browse_btn)
        layout.addLayout(media_row)

        privacy_row = QHBoxLayout()
        privacy_row.addWidget(QLabel("Quyền riêng tư:"))
        self.privacy_combo = QComboBox()
        for value, label in PRIVACY_LABELS.items():
            self.privacy_combo.addItem(label, value)
        privacy_row.addWidget(self.privacy_combo)
        layout.addLayout(privacy_row)

        toggles_row = QHBoxLayout()
        self.disable_duet_check = QCheckBox("Tắt Duet")
        self.disable_comment_check = QCheckBox("Tắt bình luận")
        self.disable_stitch_check = QCheckBox("Tắt Stitch")
        for cb in (self.disable_duet_check, self.disable_comment_check, self.disable_stitch_check):
            toggles_row.addWidget(cb)
        layout.addLayout(toggles_row)

        audit_hint = QLabel(
            "Lưu ý: nếu app TikTok của bạn CHƯA được TikTok duyệt (audit), video chỉ hiển thị ở chế độ "
            "riêng tư (Chỉ mình tôi) bất kể bạn chọn quyền riêng tư nào ở trên."
        )
        audit_hint.setObjectName("mutedHint")
        audit_hint.setWordWrap(True)
        layout.addWidget(audit_hint)

        self.post_btn = QPushButton("Đăng lên TikTok")
        self.post_btn.setObjectName("primaryButton")
        self.post_btn.clicked.connect(self._on_post)
        layout.addWidget(self.post_btn)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        arrange_cards(layout, [("Nội dung & vật liệu", [0, 1, 2, 3, 4, 5]), ("Xuất bản", [6, 7])])

    # ---------- Cross-tab wiring ----------

    def set_message(self, text: str) -> None:
        self.caption_input.setPlainText(text)

    def set_video_path(self, path: Path) -> None:
        self._video_path = path
        self.video_path_label.setText(str(path))
        self.log_message.emit(f"Đã gắn video vào bài đăng TikTok: {path}", "info")

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
        account = config.get_tiktok_account()
        if not account.get("access_token"):
            self.log_message.emit("Chưa kết nối TikTok — vào tab 'Kết nối TikTok' trước.", "error")
            return

        privacy_level = self.privacy_combo.currentData()
        privacy_label = self.privacy_combo.currentText()
        confirm = QMessageBox.question(
            self,
            "Xác nhận đăng TikTok",
            f"Bạn sắp đăng video NGAY LẬP TỨC lên TikTok (quyền riêng tư: {privacy_label}). Tiếp tục?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.post_btn.setEnabled(False)
        self.status_label.setText("Đang chuẩn bị đăng...")
        self.log_message.emit("Đang đăng video lên TikTok...", "info")
        self._worker = Worker(
            self._post_worker,
            video_path=self._video_path,
            title=self.caption_input.toPlainText().strip(),
            privacy_level=privacy_level,
            disable_duet=self.disable_duet_check.isChecked(),
            disable_comment=self.disable_comment_check.isChecked(),
            disable_stitch=self.disable_stitch_check.isChecked(),
        )
        self._worker.progress.connect(lambda msg: self.status_label.setText(msg))
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @staticmethod
    def _post_worker(
        video_path: Path,
        title: str,
        privacy_level: str,
        disable_duet: bool,
        disable_comment: bool,
        disable_stitch: bool,
        on_progress=None,
    ) -> dict:
        access_token = _ensure_valid_token(on_progress=on_progress)
        client = TikTokClient(access_token)
        return client.post_video(
            video_path,
            title=title,
            privacy_level=privacy_level,
            disable_duet=disable_duet,
            disable_comment=disable_comment,
            disable_stitch=disable_stitch,
            on_progress=on_progress,
        )

    def _on_done(self, _result: dict) -> None:
        self.post_btn.setEnabled(True)
        self.status_label.setText("Đã đăng lên TikTok thành công.")
        history_store.add_post(
            "tiktok_video", self.caption_input.toPlainText().strip(), str(self._video_path or ""), ok=True
        )
        self.log_message.emit("Đăng TikTok thành công.", "success")

    def _on_error(self, message: str) -> None:
        self.post_btn.setEnabled(True)
        self.status_label.setText("Đăng TikTok thất bại.")
        history_store.add_post(
            "tiktok_video", self.caption_input.toPlainText().strip(), str(self._video_path or ""), ok=False
        )
        self.log_message.emit(f"Lỗi đăng TikTok: {message}", "error")
