"""Browse and reuse saved content without changing the archived original."""
from __future__ import annotations
import json
import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget, QComboBox,
)

from app.storage import history_store
from app.ui.widgets.page_header import make_page_header
from app.workers.async_worker import Worker

PAGE_SIZE = 30


class ArchiveTab(QWidget):
    reuse_requested = Signal(str, str, str)  # destination, topic, text
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = 0
        self._busy = False
        self._pending = False
        self._has_more = False
        self._selected = None
        self._worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(make_page_header(
            "Kho bài viết đã đăng", "Lưu nội dung và tệp đính kèm · Xem trên điện thoại · Chỉnh sửa và đăng lại."
        ))
        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm theo chủ đề hoặc nội dung bài viết…")
        self.search_input.setAccessibleName("Tìm trong kho lưu trữ")
        self.search_input.setClearButtonEnabled(True)
        toolbar.addWidget(self.search_input, 1)
        self.source_combo = QComboBox()
        self.source_combo.addItem("Content đã tạo", "contents")
        self.source_combo.addItem("Bài đăng thành công", "posts")
        self.source_combo.setCurrentIndex(1)
        self.source_combo.setAccessibleName("Loại bài viết lưu trữ")
        self.source_combo.currentIndexChanged.connect(self._source_changed)
        toolbar.addWidget(self.source_combo)
        self.refresh_btn = QPushButton("Làm mới")
        self.refresh_btn.setObjectName("linkButton")
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)
        self.status_label = QLabel("Chọn một bài viết để đọc lại.")
        self.status_label.setObjectName("mutedHint")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.content_list = QListWidget()
        self.content_list.setObjectName("archiveList")
        self.content_list.setStyleSheet("""
            QListWidget#archiveList { border: 0; background: transparent; }
            QListWidget#archiveList::item { padding: 10px 8px; border: 1px solid transparent; border-radius: 8px; }
            QListWidget#archiveList::item:hover { background: rgba(145, 125, 205, 22); }
            QListWidget#archiveList::item:selected { background: rgba(145, 125, 205, 55); color: palette(text); border-color: rgba(145, 125, 205, 140); }
        """)
        self.content_list.setMinimumWidth(180)
        self.content_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.content_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_list.setSpacing(5)
        self.content_list.setAccessibleName("Danh sách bài viết đã lưu")
        self.content_list.currentItemChanged.connect(self._select_item)
        self.content_list.itemClicked.connect(self._show_post_dialog)
        self.content_list.itemActivated.connect(self._show_post_dialog)
        splitter.addWidget(self.content_list)
        reader = QWidget()
        reader_layout = QVBoxLayout(reader)
        reader_layout.setContentsMargins(14, 0, 0, 0)
        reader_layout.setSpacing(10)
        self.title_label = QLabel("Nội dung bài viết")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setObjectName("sectionTitle")
        self.title_label.setWordWrap(True)
        reader_layout.addWidget(self.title_label)
        self.date_label = QLabel()
        self.date_label.setObjectName("mutedHint")
        self.date_label.setWordWrap(True)
        self.date_label.setTextFormat(Qt.TextFormat.PlainText)
        reader_layout.addWidget(self.date_label)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Chọn bài viết trong danh sách để xem toàn bộ nội dung.")
        self.preview.setMinimumWidth(240)
        reader_layout.addWidget(self.preview, 1)
        published_actions = QHBoxLayout()
        self.mobile_btn = QPushButton("Xem mobile / Chỉnh sửa")
        self.mobile_btn.clicked.connect(lambda: self._show_post_dialog(self.content_list.currentItem()))
        published_actions.addWidget(self.mobile_btn)
        self.open_post_btn = QPushButton("Mở bài gốc")
        self.open_post_btn.setObjectName("linkButton")
        self.open_post_btn.clicked.connect(self._open_post)
        published_actions.addWidget(self.open_post_btn)
        self.attachments_btn = QPushButton("Ảnh / video đính kèm")
        self.attachments_btn.setObjectName("linkButton")
        self.attachments_menu = QMenu(self.attachments_btn)
        self.attachments_btn.setMenu(self.attachments_menu)
        published_actions.addWidget(self.attachments_btn, 1)
        reader_layout.addLayout(published_actions)
        actions = QHBoxLayout()
        self.copy_btn = QPushButton("Sao chép")
        self.copy_btn.setObjectName("linkButton")
        self.copy_btn.clicked.connect(self._copy)
        actions.addWidget(self.copy_btn)
        self.reuse_btn = QPushButton("Tái sử dụng")
        self.reuse_btn.setObjectName("primaryButton")
        menu = QMenu(self.reuse_btn)
        for title, destination in [
            ("Mở trong Viết Content", "content"), ("Dùng tạo ảnh", "image"),
            ("Dùng tạo video", "video"), ("Dùng đăng Facebook", "facebook"),
        ]:
            menu.addAction(title, lambda key=destination: self._reuse(key))
        self.reuse_btn.setMenu(menu)
        actions.addWidget(self.reuse_btn, 1)
        reader_layout.addLayout(actions)
        splitter.addWidget(reader)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([280, 600])
        splitter.setMinimumHeight(350)
        layout.addWidget(splitter, 1)

        pagination = QHBoxLayout()
        self.previous_btn = QPushButton("Trang trước")
        self.next_btn = QPushButton("Trang sau")
        for button in (self.previous_btn, self.next_btn):
            button.setObjectName("linkButton")
        self.previous_btn.clicked.connect(lambda: self._change_page(-1))
        self.next_btn.clicked.connect(lambda: self._change_page(1))
        self.page_label = QLabel("Trang 1")
        self.page_label.setObjectName("mutedHint")
        pagination.addWidget(self.previous_btn)
        pagination.addStretch()
        pagination.addWidget(self.page_label)
        pagination.addStretch()
        pagination.addWidget(self.next_btn)
        layout.addLayout(pagination)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self.refresh)
        self.search_input.textChanged.connect(self._search_changed)
        self._update_actions()

    def _search_changed(self):
        # Invalidate an in-flight result immediately, before the debounce expires.
        if self._busy:
            self._pending = True
        self._search_timer.start()

    def _source_changed(self):
        self._select_item(None)
        self.search_input.setPlaceholderText(
            "Tìm nội dung, tên Page hoặc mã bài đăng…" if self.source_combo.currentData() == "posts"
            else "Tìm theo chủ đề hoặc nội dung bài viết…"
        )
        self.refresh()

    def refresh(self):
        self._offset = 0
        self._load()

    def _change_page(self, direction):
        if self._busy:
            return
        self._offset = max(0, self._offset + direction * PAGE_SIZE)
        self._load()

    def _load(self):
        if self._busy:
            self._pending = True
            return
        self._search_timer.stop()
        self._busy = True
        self.status_label.setText("Đang tải bài viết…")
        self._update_actions()
        self._loading_source = self.source_combo.currentData()
        loader = history_store.list_successful_posts if self._loading_source == "posts" else history_store.list_contents
        self._worker = Worker(loader,
                              self.search_input.text().strip(), PAGE_SIZE + 1, self._offset)
        self._worker.finished.connect(self._loaded)
        self._worker.error.connect(self._failed)
        self._worker.start()

    def _finish_request(self):
        self._busy = False
        if self._pending:
            self._pending = False
            self.refresh()
            return False
        return True

    def _loaded(self, rows):
        if not self._finish_request():
            return
        previous_id = self._identity(self._selected)
        self._has_more = len(rows) > PAGE_SIZE
        self.content_list.clear()
        self._select_item(None)
        selected_index = 0
        for index, row in enumerate(rows[:PAGE_SIZE]):
            row = dict(row)
            row["source"] = self._loading_source
            if row["source"] == "posts":
                row["text"] = str(row.get("message") or "")
                if row.get("link_url"):
                    row["text"] += "\n" + row["link_url"]
                row["topic"] = " ".join(row["text"].split())[:100] or "Bài đăng có ảnh / video"
            topic = str(row.get("topic") or "Chưa có chủ đề")
            text = str(row.get("text") or "")
            date = self._date(row)
            detail = self._post_destination(row) if row["source"] == "posts" else f"{len(text.split())} từ"
            item = QListWidgetItem(f"{' '.join(topic.split())}\n{date}  ·  {detail}")
            item.setToolTip(topic)
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.content_list.addItem(item)
            if self._identity(row) == previous_id:
                selected_index = index
        if rows:
            self.content_list.setCurrentRow(selected_index)
            self.status_label.setText(
                f"Bài {self._offset + 1}–{self._offset + min(len(rows), PAGE_SIZE)}  ·  Mới nhất trước"
            )
        else:
            self.status_label.setText(
                "Không tìm thấy bài viết phù hợp. Thử từ khoá khác."
                if self.search_input.text().strip() else
                ("Chưa có bài đăng thành công được lưu. Bài đăng mới sẽ tự động xuất hiện ở đây."
                 if self.source_combo.currentData() == "posts" else
                 "Chưa có bài viết ở đây. Content được tạo sẽ tự động lưu vào kho.")
            )
        self.page_label.setText(f"Trang {self._offset // PAGE_SIZE + 1}")
        self._update_actions()

    def _failed(self, message):
        if not self._finish_request():
            return
        self.content_list.clear()
        self._select_item(None)
        self._has_more = False
        self.status_label.setText("Không tải được kho lưu trữ. Nhấn Làm mới để thử lại.")
        self.log_message.emit(f"Không tải được kho lưu trữ: {message}", "error")
        self._update_actions()

    @staticmethod
    def _identity(row):
        return (row.get("source", "contents"), str(row.get("id", row.get("_id")))) if row else None

    @staticmethod
    def _date(row):
        return str(row.get("created_at") or "").replace("T", " ")[:16]

    def _select_item(self, item, previous=None):
        self._selected = item.data(Qt.ItemDataRole.UserRole) if item else None
        row = self._selected or {}
        topic = str(row.get("topic") or "Nội dung bài viết")
        self.title_label.setText(topic[:160] + ("…" if len(topic) > 160 else ""))
        self.title_label.setToolTip(topic)
        self.date_label.setText(self._date(row))
        if row.get("source") == "posts":
            status = f"Đã lên lịch: {row['scheduled_time']}" if row.get("scheduled_time") else "Đăng thành công"
            identity = str(row.get("facebook_post_id") or "")
            self.date_label.setText(f"{self._date(row)} · {self._post_destination(row)}\n{status}" +
                                    (f" · ID: {identity}" if identity else ""))
        self.preview.setPlainText(str(row.get("text") or ""))
        self.attachments_menu.clear()
        for path in self._attachment_paths(row):
            exists = path.is_file()
            action = self.attachments_menu.addAction(path.name + ("" if exists else " — không tìm thấy tệp"))
            action.setEnabled(exists)
            action.triggered.connect(lambda checked=False, p=path: self._open_local(p))
        self._update_actions()

    @staticmethod
    def _post_destination(row):
        kind = str(row.get("post_type") or "")
        platform = "YouTube" if kind.startswith("youtube") else "TikTok" if kind.startswith("tiktok") else "Facebook"
        name = row.get("page_name") or row.get("page_id")
        return f"{platform} · {name}" if name and name != platform else platform

    @staticmethod
    def _attachment_paths(row):
        value = row.get("attachment_path") or ""
        if not value:
            return []
        if row.get("post_type") == "photos":
            try:
                values = json.loads(value)
                return [Path(p) for p in values if isinstance(p, str) and p] if isinstance(values, list) else []
            except (TypeError, ValueError):
                return []
        return [Path(value)]

    @staticmethod
    def _post_url(row):
        identity = str(row.get("facebook_post_id") or "")
        kind = str(row.get("post_type") or "")
        if kind.startswith("youtube") and re.fullmatch(r"[A-Za-z0-9_-]+", identity):
            return f"https://www.youtube.com/watch?v={identity}"
        if not kind.startswith(("tiktok", "youtube")) and re.fullmatch(r"[0-9_]+", identity):
            return f"https://www.facebook.com/{identity}"
        return ""

    def _open_post(self):
        url = self._post_url(self._selected or {})
        if url and not QDesktopServices.openUrl(QUrl(url)):
            self.log_message.emit("Không mở được liên kết bài viết.", "error")

    def _show_post_dialog(self, item):
        if self._busy or item is None:
            return
        row = item.data(Qt.ItemDataRole.UserRole)
        if row.get("source") != "posts":
            return
        from app.ui.published_post_dialog import PublishedPostDialog
        try:
            dialog = PublishedPostDialog(row, self)
            dialog.changed.connect(self.refresh)
            dialog.exec()
            dialog.deleteLater()
        except Exception as exc:
            self.log_message.emit(f"Không mở được bài viết: {exc}", "error")

    def _open_local(self, path):
        if not path.is_file() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            self.log_message.emit("Không mở được tệp đính kèm. Tệp có thể đã bị xoá hoặc di chuyển.", "error")

    def _update_actions(self):
        usable = bool(self._selected and self._selected.get("text")) and not self._busy
        self.copy_btn.setEnabled(usable)
        self.reuse_btn.setEnabled(usable)
        posted = bool(self._selected and self._selected.get("source") == "posts")
        self.mobile_btn.setVisible(posted)
        self.mobile_btn.setEnabled(posted and not self._busy)
        self.open_post_btn.setVisible(posted)
        self.attachments_btn.setVisible(posted)
        self.open_post_btn.setEnabled(not self._busy and bool(self._post_url(self._selected or {})))
        self.attachments_btn.setEnabled(not self._busy and bool(self.attachments_menu.actions()))
        self.content_list.setEnabled(not self._busy)
        self.refresh_btn.setEnabled(not self._busy)
        self.previous_btn.setEnabled(not self._busy and self._offset > 0)
        self.next_btn.setEnabled(not self._busy and self._has_more)

    def _copy(self):
        if self._selected:
            QApplication.clipboard().setText(str(self._selected.get("text") or ""))
            self.log_message.emit("Đã sao chép nội dung bài viết.", "success")

    def _reuse(self, destination):
        if self._selected:
            self.reuse_requested.emit(destination, str(self._selected.get("topic") or ""),
                                      str(self._selected.get("text") or ""))
