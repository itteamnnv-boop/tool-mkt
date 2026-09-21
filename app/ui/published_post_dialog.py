"""Mobile preview and explicit edit/repost/update actions."""
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QLabel, QTextEdit,
                               QPushButton, QMessageBox, QComboBox)
from app import config
from app.core.archived_posts import platform_for, repost, update_original
from app.storage import history_store
from app.storage.post_assets import attachment_paths
from app.ui.widgets.facebook_post_preview import FacebookPostPreview
from app.workers.async_worker import Worker


class PublishedPostDialog(QDialog):
    changed = Signal()

    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.row = dict(row)
        self._busy = False
        self._worker = None
        self._player = None
        self.setWindowTitle("Bài viết đã đăng · Xem trước và chỉnh sửa")
        self.resize(940, 760)
        root = QHBoxLayout(self)
        self.phone = FacebookPostPreview()
        root.addWidget(self.phone)
        panel = QVBoxLayout()
        root.addLayout(panel, 1)
        platform = platform_for(row)
        label = QLabel(f"{platform.title()} · {row.get('page_name') or row.get('page_id') or 'Tài khoản đã đăng'}")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        panel.addWidget(label)
        note = QLabel("Sửa và lưu bản nháp trong kho; chọn Đăng lại để tạo bài mới hoặc Cập nhật để sửa nội dung bài gốc. Ảnh/video được giữ nguyên.")
        note.setWordWrap(True)
        panel.addWidget(note)
        if row.get("link_url"):
            link_note = QLabel("Link đính kèm (giữ lại khi đăng lại): " + row["link_url"])
            link_note.setTextFormat(Qt.TextFormat.PlainText)
            link_note.setWordWrap(True)
            panel.addWidget(link_note)
        self.editor = QTextEdit()
        draft = row.get("draft_message")
        self.editor.setPlainText(draft if draft is not None else row.get("message", ""))
        panel.addWidget(self.editor, 1)
        self.files = QComboBox()
        self.paths = attachment_paths(row)
        for path in self.paths:
            self.files.addItem(path.name + ("" if path.is_file() else " — thiếu tệp"))
        self.files.setVisible(bool(self.paths))
        panel.addWidget(self.files)
        self.open_file = QPushButton("Mở tệp ảnh / phát video")
        self.open_file.setVisible(bool(self.paths))
        self.open_file.clicked.connect(self._open_file)
        panel.addWidget(self.open_file)
        self.status = QLabel("Bản xem trước minh hoạ; giao diện thực tế tuỳ nền tảng.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        panel.addWidget(self.status)
        self.save_btn = QPushButton("Lưu bản chỉnh sửa")
        self.repost_btn = QPushButton("Đăng lại thành bài mới")
        self.update_btn = QPushButton("Cập nhật nội dung bài gốc")
        self.close_btn = QPushButton("Đóng")
        for button in (self.save_btn, self.repost_btn, self.update_btn, self.close_btn):
            panel.addWidget(button)
        self.save_btn.clicked.connect(self._save)
        self.repost_btn.clicked.connect(self._repost)
        self.update_btn.clicked.connect(self._update)
        self.close_btn.clicked.connect(self.close)
        self.can_update = platform != "tiktok" and bool(row.get("facebook_post_id"))
        self.update_btn.setEnabled(self.can_update)
        if platform == "tiktok":
            self.update_btn.setToolTip("Chưa hỗ trợ cập nhật bài TikTok; dùng Đăng lại.")
            self.status.setText("TikTok: hỗ trợ lưu bản chỉnh sửa và đăng lại; chưa hỗ trợ cập nhật bài gốc.")
        self.phone.set_page(row.get("page_name") or platform.title())
        self.phone.meta.setText("Bản xem trước bài trong kho")
        if platform != "facebook":
            self.phone.phone.findChild(QLabel, "facebookWordmark").setText(platform.title())
        self.editor.textChanged.connect(self._preview)
        self.files.currentIndexChanged.connect(self._preview)
        self._preview()
        if self.paths and "video" in row["post_type"] and self.paths[0].is_file():
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            # Paint frames into the existing phone widget. Native video widgets
            # do not reliably render inside its QGraphicsProxyWidget.
            self._video_sink = QVideoSink(self)
            self._video_sink.videoFrameChanged.connect(self._video_frame)
            self._player.setVideoSink(self._video_sink)
            self._player.setSource(QUrl.fromLocalFile(str(self.paths[0].resolve())))
            self._player.errorOccurred.connect(lambda *args: self.status.setText(
                "Không phát được video trong preview. Dùng Mở tệp để phát bằng ứng dụng trên máy."))
            self.play_btn = QPushButton("Phát / Tạm dừng video")
            self.play_btn.clicked.connect(self._toggle_video)
            panel.insertWidget(4, self.play_btn)
        self._saved_text = self.editor.toPlainText()

    def _video_frame(self, frame):
        image = frame.toImage()
        if not image.isNull():
            self.phone.media.setPixmap(QPixmap.fromImage(image))

    def _toggle_video(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _preview(self):
        self.phone.set_content(self.editor.toPlainText())
        if self._player:
            return
        index = self.files.currentIndex()
        path = self.paths[index] if index >= 0 else None
        if self.row["post_type"] in ("photo", "photos") and path:
            self.phone.set_media(QPixmap(str(path)), image_count=len(self.paths))
            self.phone.video_caption.setText(f"Ảnh {index + 1}/{len(self.paths)} · Chọn tệp để xem các ảnh khác")
        else:
            self.phone.set_media(video=path.name if path else "")

    def _open_file(self):
        index = self.files.currentIndex()
        if index < 0:
            return
        path = self.paths[index]
        if not path.is_file() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            self.status.setText("Không mở được tệp. Tệp có thể đã bị di chuyển hoặc xoá.")

    def _set_busy(self, busy):
        self._busy = busy
        self.editor.setReadOnly(busy)
        for button in (self.save_btn, self.repost_btn, self.close_btn):
            button.setEnabled(not busy)
        self.update_btn.setEnabled(not busy and self.can_update)

    def _run(self, fn, *args):
        if self._busy:
            return
        self._set_busy(True)
        self.status.setText("Đang xử lý…")
        self._worker = Worker(fn, *args)
        self._worker.finished.connect(self._done)
        self._worker.error.connect(self._error)
        self._worker.progress.connect(self.status.setText)
        self._worker.start()

    def _save(self):
        self._run(history_store.save_post_draft, self.row, self.editor.toPlainText())

    def _repost(self):
        settings = config.load_settings()
        platform = platform_for(self.row)
        destination = self.row.get("page_name") or self.row.get("page_id") or "Page gốc"
        detail = ""
        if platform == "youtube":
            destination = config.get_youtube_account().get("channel_title") or "YouTube đang kết nối"
            detail = "\nQuyền riêng tư: " + settings.get("automation_youtube_privacy", "private")
            title = settings.get("automation_youtube_title", "").strip() or self.editor.toPlainText().split("\n")[0][:100] or "Video mới"
            detail += "\nTiêu đề: " + title
        elif platform == "tiktok":
            destination = config.get_tiktok_account().get("display_name") or "TikTok đang kết nối"
            detail = "\nQuyền riêng tư: " + settings.get("automation_tiktok_privacy", "SELF_ONLY")
        if QMessageBox.question(self, "Đăng lại", f"Tạo bài mới ngay trên {destination}?{detail}") == QMessageBox.StandardButton.Yes:
            self._run(repost, self.row, self.editor.toPlainText(), settings)

    def _update(self):
        if not self.can_update:
            return
        if QMessageBox.question(self, "Cập nhật bài gốc", "Cập nhật nội dung bài " +
                                str(self.row.get("facebook_post_id")) + " trên nền tảng? Ảnh/video giữ nguyên.") == QMessageBox.StandardButton.Yes:
            self._run(update_original, self.row, self.editor.toPlainText())

    def _done(self, result):
        self._set_busy(False)
        self._saved_text = self.editor.toPlainText()
        self.status.setText(result or "Đã lưu bản chỉnh sửa trong kho. Bài gốc trên nền tảng chưa thay đổi.")
        self.changed.emit()

    def _error(self, message):
        self._set_busy(False)
        self.status.setText("Không hoàn tất: " + message)

    def reject(self):
        self.close()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
            return
        if self.editor.toPlainText() != self._saved_text:
            answer = QMessageBox.question(self, "Chỉnh sửa chưa lưu", "Đóng và bỏ phần chỉnh sửa chưa lưu?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        super().closeEvent(event)
        if event.isAccepted() and self._player:
            self._player.stop()
