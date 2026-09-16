"""Tab: connect Facebook Pages by pasting a User Access Token (from Graph API Explorer),
then manage the list of Pages available for posting."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.facebook_client import extract_access_token, fetch_pages_with_token
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.ui.widgets.row_list import RowListWidget
from app.workers.async_worker import Worker


class FacebookConnectTab(QWidget):
    pages_changed = Signal()
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Worker | None = None
        self._build_ui()
        self.refresh_pages_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        layout.addWidget(
            make_page_header(
                "🔗 Kết nối Facebook",
                "Dán 1 User Access Token để lấy token của TẤT CẢ Page bạn quản lý — không cần tự tìm "
                "token của từng Page. Sau đó chọn Page cần đăng ở tab Đăng Facebook.",
            )
        )

        token_hint = QLabel(
            "Lấy token tại Graph API Explorer (developers.facebook.com/tools/explorer), "
            "chọn App của bạn, quyền: pages_show_list, pages_read_engagement, pages_manage_posts:"
        )
        token_hint.setWordWrap(True)
        layout.addWidget(token_hint)
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("Dán User Access Token vào đây...")
        layout.addWidget(self.token_input)

        self.connect_btn = QPushButton("Kết nối & Tải danh sách Page")
        self.connect_btn.setObjectName("primaryButton")
        self.connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(self.connect_btn)

        layout.addWidget(QLabel("Các Page đã kết nối:"))
        self.pages_list = RowListWidget(height=220)
        layout.addWidget(self.pages_list)
        # Dồn phần diện tích thừa xuống cuối trang thay vì để QVBoxLayout
        # phân bổ thành các khoảng trống lớn giữa từng điều khiển.
        layout.addStretch(1)
        arrange_cards(layout, [("Kết nối tài khoản", [0, 1, 2]), ("Các Page đã kết nối", [4])])

    def _on_connect(self) -> None:
        pasted = self.token_input.text().strip()
        if not pasted:
            self.log_message.emit("Vui lòng dán User Access Token.", "error")
            return
        access_token = extract_access_token(pasted)

        settings = config.load_settings()
        app_id = settings.get("facebook_app_id", "")
        app_secret = config.get_secret("facebook_app_secret")

        self.connect_btn.setEnabled(False)
        self.log_message.emit("Đang kết nối tới Facebook...", "info")
        self._worker = Worker(fetch_pages_with_token, access_token=access_token, app_id=app_id, app_secret=app_secret)
        self._worker.progress.connect(lambda msg: self.log_message.emit(msg, "info"))
        self._worker.finished.connect(self._on_connected)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_connected(self, pages: list[dict]) -> None:
        self.connect_btn.setEnabled(True)
        if not pages:
            self.log_message.emit("Token hợp lệ nhưng không tìm thấy Page nào bạn quản lý.", "error")
            return

        valid_pages = []
        skipped_names = []
        for page in pages:
            page_id = page.get("id")
            token = page.get("access_token")
            if not page_id or not token:
                skipped_names.append(page.get("name") or page_id or "(không rõ)")
                continue
            config.set_page_token(page_id, token)
            valid_pages.append(page)

        if valid_pages:
            config.upsert_pages(valid_pages)
            self.token_input.clear()
            self.refresh_pages_list()
            self.pages_changed.emit()
            names = ", ".join(p.get("name") or p.get("id", "?") for p in valid_pages)
            self.log_message.emit(f"Đã kết nối {len(valid_pages)} Page: {names}", "success")

        if skipped_names:
            self.log_message.emit(
                f"Bỏ qua {len(skipped_names)} Page thiếu quyền truy cập (access_token): "
                + ", ".join(skipped_names),
                "error",
            )

    def _on_error(self, message: str) -> None:
        self.connect_btn.setEnabled(True)
        self.log_message.emit(f"Lỗi kết nối Facebook: {message}", "error")

    def refresh_pages_list(self) -> None:
        self.pages_list.clear()
        pages = config.list_pages()
        if not pages:
            placeholder = QLabel("Chưa kết nối Page nào. Dán User Access Token ở trên để bắt đầu.")
            placeholder.setObjectName("mutedHint")
            self.pages_list.add_row(placeholder)
            return
        for page in pages:
            self.pages_list.add_row(self._make_page_row(page))

    def _make_page_row(self, page: dict) -> QWidget:
        page_id = page.get("id", "?")
        page_name = page.get("name") or page_id
        row = QWidget()
        row.setObjectName("pageRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 6, 10, 6)
        label = QLabel(f"<b>{page_name}</b><br><span style='color:#a3b3bf;'>ID: {page_id}</span>")
        label.setWordWrap(True)
        h.addWidget(label, stretch=1)
        remove_btn = QPushButton("Xoá")
        remove_btn.setObjectName("linkButton")
        remove_btn.clicked.connect(lambda: self._on_remove(page_id))
        h.addWidget(remove_btn)
        return row

    def _on_remove(self, page_id: str) -> None:
        config.remove_page(page_id)
        self.refresh_pages_list()
        self.pages_changed.emit()
        self.log_message.emit("Đã gỡ kết nối Page.", "info")
