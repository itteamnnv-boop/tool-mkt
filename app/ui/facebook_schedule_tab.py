"""Facebook schedules created by this app, with explicit remote status checks."""
from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from app.core.facebook_schedule import schedule_time, status_data, status_label, sync_posts
from app.storage import history_store
from app.ui.archive_tab import ArchiveTab
from app.ui.widgets.page_header import make_page_header
from app.workers.async_worker import Worker

PAGE_SIZE = 30


class FacebookScheduleTab(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._offset = 0
        self._busy = False
        self._pending = False
        self._more = False
        self._worker = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(make_page_header("Quản lý lịch đăng Facebook",
            "Các lịch đã tạo trong ứng dụng · Kiểm tra trạng thái thực tế từ Facebook."))
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm nội dung, tên Page hoặc mã bài…")
        self.search.setClearButtonEnabled(True)
        toolbar.addWidget(self.search, 1)
        self.refresh_btn = QPushButton("Tải danh sách")
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_btn)
        self.sync_btn = QPushButton("Cập nhật trạng thái trang này")
        self.sync_btn.clicked.connect(lambda: self._sync(self._rows))
        toolbar.addWidget(self.sync_btn)
        root.addLayout(toolbar)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setObjectName("facebookScheduleTable")
        self.table.setStyleSheet("""
            QTableWidget#facebookScheduleTable { background: transparent; gridline-color: rgba(140,140,140,40); }
            QTableWidget#facebookScheduleTable::item { padding: 6px; }
            QTableWidget#facebookScheduleTable::item:selected { background: rgba(75,125,185,110); }
        """)
        self.table.setHorizontalHeaderLabels(["Lịch đăng (giờ máy)", "Page", "Nội dung", "Trạng thái đăng"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setWordWrap(False)
        self.table.setMinimumHeight(220)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 145)
        self.table.setColumnWidth(3, 240)
        self.table.itemSelectionChanged.connect(self._select)
        root.addWidget(self.table, 2)
        self.detail = QLabel("Chọn bài để xem toàn bộ nội dung và thông tin trạng thái.")
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        self.detail.setWordWrap(True)
        root.addWidget(self.detail)
        self.content = QTextEdit()
        self.content.setReadOnly(True)
        self.content.setMinimumHeight(130)
        root.addWidget(self.content, 1)
        actions = QHBoxLayout()
        self.check_btn = QPushButton("Kiểm tra bài đang chọn")
        self.check_btn.clicked.connect(lambda: self._sync([self._selected()] if self._selected() else []))
        self.preview_btn = QPushButton("Xem mobile / ảnh, video")
        self.preview_btn.clicked.connect(self._preview)
        self.open_btn = QPushButton("Mở trên Facebook")
        self.open_btn.clicked.connect(self._open)
        for button in (self.check_btn, self.preview_btn, self.open_btn):
            actions.addWidget(button)
        root.addLayout(actions)
        pagination = QHBoxLayout()
        self.previous_btn = QPushButton("Trang trước")
        self.next_btn = QPushButton("Trang sau")
        self.previous_btn.clicked.connect(lambda: self._page(-1))
        self.next_btn.clicked.connect(lambda: self._page(1))
        self.page_label = QLabel("Trang 1")
        pagination.addWidget(self.previous_btn)
        pagination.addStretch()
        pagination.addWidget(self.page_label)
        pagination.addStretch()
        pagination.addWidget(self.next_btn)
        root.addLayout(pagination)
        note = QLabel("Đến giờ hẹn không đồng nghĩa đã đăng. “Đã đăng” chỉ xuất hiện khi Facebook xác nhận. "
                      "Lỗi kết nối/thiếu quyền không có nghĩa bài đã thất bại hoặc bị xoá.")
        note.setWordWrap(True)
        root.addWidget(note)
        for button in (self.refresh_btn, self.check_btn, self.preview_btn, self.open_btn,
                       self.previous_btn, self.next_btn):
            button.setObjectName("linkButton")
        self.sync_btn.setObjectName("primaryButton")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self._search_timer.start())
        self._clock = QTimer(self)
        self._clock.setInterval(60000)
        self._clock.timeout.connect(self._tick)
        self._clock.start()
        self._controls()

    def _selected(self):
        index = self.table.currentRow()
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def _controls(self):
        selected = self._selected()
        for widget in (self.search, self.refresh_btn, self.table):
            widget.setEnabled(not self._busy)
        self.sync_btn.setEnabled(not self._busy and any(row.get("ok") for row in self._rows))
        self.check_btn.setEnabled(not self._busy and bool(selected and selected.get("ok")))
        self.preview_btn.setEnabled(not self._busy and bool(selected))
        self.open_btn.setEnabled(not self._busy and bool(ArchiveTab._post_url(selected or {})))
        self.previous_btn.setEnabled(not self._busy and self._offset > 0)
        self.next_btn.setEnabled(not self._busy and self._more)

    def refresh(self):
        if self._busy:
            self._pending = True
            return
        self._offset = 0
        self._load()

    def _page(self, direction):
        if not self._busy:
            self._offset = max(0, self._offset + direction * PAGE_SIZE)
            self._load()

    def _start(self, fn, callback, *args):
        self._busy = True
        self._controls()
        self._worker = Worker(fn, *args)
        self._worker.finished.connect(callback)
        self._worker.error.connect(self._failed)
        self._worker.progress.connect(self.summary.setText)
        self._worker.start()

    def _load(self):
        self._search_timer.stop()
        self.summary.setText("Đang tải lịch đăng…")
        self._start(history_store.list_scheduled_posts, self._loaded,
                    self.search.text().strip(), PAGE_SIZE + 1, self._offset)

    def _finish(self):
        self._busy = False
        self._controls()
        if self._pending:
            self._pending = False
            self.refresh()

    def _loaded(self, rows):
        self._more = len(rows) > PAGE_SIZE
        self._rows = rows[:PAGE_SIZE]
        self._render()
        self._finish()

    def _render(self):
        index = max(0, self.table.currentRow())
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        counts = {}
        for number, row in enumerate(self._rows):
            state = status_data(row)
            label = status_label(row)
            counts[label] = counts.get(label, 0) + 1
            scheduled = schedule_time(row)
            text = state.get("message", row.get("message") or "")
            values = [scheduled.strftime("%d/%m/%Y %H:%M") if scheduled else str(row.get("scheduled_time") or ""),
                      row.get("page_name") or row.get("page_id") or "Không rõ Page",
                      " ".join(text.split())[:160] or "Bài có ảnh/video", label + (" · lỗi kiểm tra" if state.get("sync_error") else "")]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value if column != 2 else text)
                self.table.setItem(number, column, item)
            font = self.table.item(number, 3).font()
            font.setBold(True)
            self.table.item(number, 3).setFont(font)
        self.table.blockSignals(False)
        if self._rows:
            self.table.selectRow(min(index, len(self._rows) - 1))
        self._select()
        self.page_label.setText(f"Trang {self._offset // PAGE_SIZE + 1}")
        self.summary.setText(" · ".join(f"{key}: {value}" for key, value in counts.items()) + " (trang này)" if counts else
                             "Không có lịch phù hợp." if self.search.text().strip() else "Chưa có lịch đăng Facebook trong ứng dụng.")

    def _select(self):
        row = self._selected()
        state = status_data(row or {})
        self.content.setPlainText(state.get("message", (row or {}).get("message") or ""))
        if row and row.get("link_url"):
            self.content.setPlainText(self.content.toPlainText() + "\n\nLink: " + row["link_url"])
        if row:
            source = "Nội dung gần nhất từ Facebook" if "message" in state else "Nội dung khi tạo lịch"
            checked = state.get("checked_at") or "Chưa kiểm tra"
            self.detail.setText(f"{status_label(row)} · ID: {row.get('facebook_post_id') or 'Chưa có'}\n"
                                f"{source} · Xác minh gần nhất: {checked}" +
                                ("\nFacebook xác nhận chưa xuất bản tại lần kiểm tra gần nhất." if state.get("published") is False else "") +
                                (f"\nLỗi tạo lịch: {state['error']}" if state.get("error") else "") +
                                (f"\nKhông kiểm tra được: {state['sync_error']}" if state.get("sync_error") else ""))
        else:
            self.detail.setText("Chọn bài để xem toàn bộ nội dung và thông tin trạng thái.")
        self._controls()

    def _sync(self, rows):
        if self._busy or not rows:
            return
        self._start(sync_posts, self._synced, [dict(row) for row in rows])

    def _synced(self, rows):
        updates = {str(row.get("id", row.get("_id"))): row for row in rows}
        self._rows = [updates.get(str(row.get("id", row.get("_id"))), row) for row in self._rows]
        self._render()
        errors = sum(bool(status_data(row).get("sync_error")) for row in rows)
        self.summary.setText(f"Đã kiểm tra {len(rows)} bài · {errors} bài cần kiểm tra lại.")
        self._finish()

    def _failed(self, message):
        self.summary.setText("Không hoàn tất: " + message)
        self.log_message.emit("Lịch đăng Facebook: " + message, "error")
        self._finish()

    def _tick(self):
        if self.isVisible() and not self._busy:
            self._render()

    def _open(self):
        url = ArchiveTab._post_url(self._selected() or {})
        if url and not QDesktopServices.openUrl(QUrl(url)):
            self.log_message.emit("Không mở được Facebook.", "error")

    def _preview(self):
        row = self._selected()
        if not row:
            return
        from app.ui.published_post_dialog import PublishedPostDialog
        try:
            dialog = PublishedPostDialog(row, self)
            dialog.setWindowTitle("Lịch đăng Facebook · Xem nội dung")
            dialog.phone.meta.setText(status_label(row))
            dialog.changed.connect(self.refresh)
            dialog.exec()
            dialog.deleteLater()
        except Exception as exc:
            self.log_message.emit(f"Không mở được nội dung: {exc}", "error")
