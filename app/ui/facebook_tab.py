"""Tab 4: soạn & đăng bài cùng lúc lên nhiều Facebook Page qua Graph API."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDateTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
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

from app.core.facebook_schedule import post_and_record
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.ui.widgets.pages_selector import PagesSelectorWidget
from app.workers.async_worker import Worker
from app.ui.widgets.processing_dialog import ProcessingDialog

ATTACHMENT_NONE = "Không đính kèm (chỉ text/link)"
ATTACHMENT_IMAGE = "Ảnh"
ATTACHMENT_VIDEO = "Video"


class FacebookTab(QWidget):
    log_message = Signal(str, str)
    schedules_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._posting = False
        self._image_path: Path | None = None
        self._video_path: Path | None = None
        self._worker: Worker | None = None
        self._build_ui()
        self.processing_dialog = ProcessingDialog(self)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(
            make_page_header("📤 Đăng Facebook", "Soạn bài, chọn 1 hoặc nhiều Page, rồi đăng cùng lúc.")
        )

        self.pages_selector = PagesSelectorWidget()
        layout.addWidget(self.pages_selector)

        layout.addWidget(QLabel("Nội dung bài đăng:"))
        self.message_input = QTextEdit()
        layout.addWidget(self.message_input)

        layout.addWidget(QLabel("Link đính kèm (chỉ dùng khi không đính kèm ảnh/video):"))
        self.link_input = QLineEdit()
        layout.addWidget(self.link_input)

        row = QHBoxLayout()
        row.addWidget(QLabel("Loại đính kèm:"))
        self.attachment_combo = QComboBox()
        self.attachment_combo.addItems([ATTACHMENT_NONE, ATTACHMENT_IMAGE, ATTACHMENT_VIDEO])
        row.addWidget(self.attachment_combo)
        layout.addLayout(row)

        media_row = QVBoxLayout()
        self.media_path_label = QLabel("(chưa chọn file)")
        self.media_path_label.setWordWrap(True)
        self.browse_btn = QPushButton("Chọn file khác...")
        self.browse_btn.clicked.connect(self._on_browse)
        media_row.addWidget(self.media_path_label, stretch=1)
        media_row.addWidget(self.browse_btn)
        layout.addLayout(media_row)

        schedule_row = QVBoxLayout()
        self.schedule_check = QCheckBox("Lên lịch đăng thay vì đăng ngay")
        self.schedule_check.toggled.connect(self._on_schedule_toggled)
        schedule_row.addWidget(self.schedule_check)
        self.schedule_datetime = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule_datetime.setCalendarPopup(True)
        self.schedule_datetime.setEnabled(False)
        schedule_row.addWidget(self.schedule_datetime)
        layout.addLayout(schedule_row)

        self.post_btn = QPushButton("Đăng bài")
        self.post_btn.setObjectName("primaryButton")
        self.post_btn.clicked.connect(self._on_post)
        layout.addWidget(self.post_btn)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        self.message_input.setMinimumHeight(160)
        arrange_cards(layout, [("Nội dung bài đăng", [1, 2, 3, 4]), ("Xuất bản", [0, 5, 6, 7, 8, 9, 10])])
        self.schedules_btn = QPushButton("Quản lý lịch đăng Facebook")
        self.schedules_btn.clicked.connect(self.schedules_requested.emit)
        layout.addWidget(self.schedules_btn)

    # ---------- Attachments ----------

    def _on_schedule_toggled(self, checked: bool) -> None:
        self.schedule_datetime.setEnabled(checked)

    def _on_browse(self) -> None:
        attachment = self.attachment_combo.currentText()
        if attachment == ATTACHMENT_IMAGE:
            path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh", "", "Images (*.png *.jpg *.jpeg)")
            if path:
                self._image_path = Path(path)
                self.media_path_label.setText(str(self._image_path))
        elif attachment == ATTACHMENT_VIDEO:
            path, _ = QFileDialog.getOpenFileName(self, "Chọn video", "", "Videos (*.mp4 *.mov)")
            if path:
                self._video_path = Path(path)
                self.media_path_label.setText(str(self._video_path))
        else:
            self.log_message.emit("Chọn loại đính kèm là Ảnh hoặc Video trước.", "info")

    def set_message(self, text: str) -> None:
        self.message_input.setPlainText(text)

    def set_image_path(self, path: Path) -> None:
        self._image_path = path
        self.attachment_combo.setCurrentText(ATTACHMENT_IMAGE)
        self.media_path_label.setText(str(path))
        self.log_message.emit(f"Đã gắn ảnh vào bài đăng: {path}", "info")

    def set_video_path(self, path: Path) -> None:
        self._video_path = path
        self.attachment_combo.setCurrentText(ATTACHMENT_VIDEO)
        self.media_path_label.setText(str(path))
        self.log_message.emit(f"Đã gắn video vào bài đăng: {path}", "info")

    # ---------- Posting ----------

    def _on_post(self) -> None:
        if self._posting:
            return
        message = self.message_input.toPlainText().strip()
        attachment = self.attachment_combo.currentText()
        if not message and not self.link_input.text().strip() and attachment == ATTACHMENT_NONE:
            self.log_message.emit("Vui lòng nhập nội dung bài đăng.", "error")
            return
        if attachment == ATTACHMENT_IMAGE and (not self._image_path or not self._image_path.is_file()):
            self.log_message.emit("Chưa chọn ảnh để đăng.", "error")
            return
        if attachment == ATTACHMENT_VIDEO and (not self._video_path or not self._video_path.is_file()):
            self.log_message.emit("Chưa chọn video để đăng.", "error")
            return

        pages = self.pages_selector.selected_pages()
        if not pages:
            self.log_message.emit(
                "Chưa chọn Page nào (hoặc Page chưa có token hợp lệ) — vào tab 'Kết nối Facebook' trước.", "error"
            )
            return

        scheduled_time = None
        schedule_label = ""
        if self.schedule_check.isChecked():
            dt: datetime = self.schedule_datetime.dateTime().toPython()
            min_allowed = datetime.now() + timedelta(minutes=10)
            if dt < min_allowed:
                self.log_message.emit("Facebook yêu cầu thời gian lên lịch tối thiểu 10 phút sau hiện tại.", "error")
                return
            scheduled_time = int(dt.timestamp())
            schedule_label = dt.isoformat(timespec="minutes")

        if not self.schedule_check.isChecked():
            page_names = ", ".join(p["name"] for p in pages)
            confirm = QMessageBox.question(
                self,
                "Xác nhận đăng bài",
                f"Bạn sắp đăng bài NGAY LẬP TỨC lên {len(pages)} Page thật: {page_names}. Tiếp tục?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        self._set_posting(True)
        self.log_message.emit(f"Đang đăng bài lên {len(pages)} Page...", "info")
        self.result_label.setText("")
        self.status_label.setText(f"Đang chuẩn bị đăng lên {len(pages)} Page...")

        if attachment == ATTACHMENT_IMAGE:
            post_type = "photo"
            kwargs = {"image_path": self._image_path, "caption": message, "scheduled_time": scheduled_time}
        elif attachment == ATTACHMENT_VIDEO:
            post_type = "video"
            kwargs = {"video_path": self._video_path, "description": message, "scheduled_time": scheduled_time}
        else:
            post_type = "text"
            kwargs = {
                "message": message,
                "link": self.link_input.text().strip() or None,
                "scheduled_time": scheduled_time,
            }

        attachment_path = str(self._image_path or "") if post_type == "photo" else str(self._video_path or "") if post_type == "video" else ""
        self._worker = Worker(post_and_record, pages=pages, post_type=post_type, content=message,
                              attachment_path=attachment_path, **kwargs)
        self._worker.progress.connect(lambda msg: self.status_label.setText(msg))
        self._worker.finished.connect(lambda results: self._on_done(post_type, message, schedule_label, results))
        self._worker.error.connect(self._on_error)
        self.processing_dialog.track(self._worker, f"Đang đăng bài lên {len(pages)} Page Facebook...")
        self._worker.start()

    def _on_done(self, post_type: str, message: str, schedule_label: str, results: list[dict]) -> None:
        self._set_posting(False)

        ok_count = sum(1 for r in results if r["ok"])
        uncertain_count = sum(bool(r.get("uncertain")) for r in results)
        fail_count = len(results) - ok_count - uncertain_count
        lines = []
        for r in results:
            if r["ok"]:
                outcome = f"đã nhận lịch {schedule_label}, chờ đăng" if schedule_label else "đăng thành công"
                lines.append(f"✓ {r['name']}: {outcome} (id={r['post_id']})")
                self.log_message.emit(f"{r['name']}: {outcome} (id={r['post_id']}).", "success")
            else:
                outcome = "chưa xác nhận" if r.get("uncertain") else "thất bại"
                lines.append(f"✗ {r['name']}: {outcome}: {r['error']}")
                self.log_message.emit(f"Đăng '{r['name']}' {outcome}: {r['error']}", "error")
            if r.get("archive_error"):
                warning = f"{r['name']}: chưa lưu đầy đủ vào kho/lịch: {r['archive_error']}"
                lines.append(warning)
                self.log_message.emit(warning, "error")

        self.status_label.setText(f"Lên lịch: {ok_count} được nhận, {fail_count} thất bại. Xem Quản lý lịch đăng Facebook để kiểm tra trạng thái."
                                 if schedule_label else f"Hoàn tất: {ok_count} thành công, {fail_count} thất bại.")
        self.result_label.setText("\n".join(lines))
        if uncertain_count:
            self.status_label.setText(self.status_label.text() + f" {uncertain_count} bài chưa xác nhận; kiểm tra Page trước khi thử lại.")

    def _set_posting(self, busy):
        self._posting = busy
        self.message_input.setReadOnly(busy)
        for widget in (self.post_btn, self.link_input, self.attachment_combo, self.browse_btn,
                       self.pages_selector, self.schedule_check):
            widget.setEnabled(not busy)
        self.schedule_datetime.setEnabled(not busy and self.schedule_check.isChecked())

    def _on_error(self, message: str) -> None:
        self._set_posting(False)
        self.status_label.setText("Đăng bài thất bại.")
        self.log_message.emit(f"Lỗi đăng bài: {message}", "error")
