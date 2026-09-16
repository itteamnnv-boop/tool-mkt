"""Tab: connect a YouTube channel via Google OAuth (desktop PKCE flow)."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from app import config
from app.core.youtube_client import authorize_and_get_tokens
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.workers.async_worker import Worker


class YouTubeConnectTab(QWidget):
    account_changed = Signal()
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Worker | None = None
        self._build_ui()
        self._refresh_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        layout.addWidget(
            make_page_header(
                "🔗 Kết nối YouTube",
                "Đăng nhập Google bằng trình duyệt (OAuth) để lấy quyền tải video lên kênh của bạn.",
            )
        )

        setup_hint = QLabel(
            "1. Tạo project tại console.cloud.google.com → bật 'YouTube Data API v3'.\n"
            "2. Vào 'APIs & Services → OAuth consent screen', thêm chính Gmail của bạn vào mục 'Test users'.\n"
            "3. Vào 'Credentials' → Create Credentials → OAuth client ID → chọn loại 'Desktop app'.\n"
            "   (loại Desktop app không cần khai báo Redirect URI — Google tự chấp nhận cổng cục bộ.)\n"
            "4. Sang tab Cài đặt, dán Client ID/Client Secret của app đó.\n"
            "5. Quay lại đây, bấm 'Đăng nhập Google/YouTube'."
        )
        setup_hint.setWordWrap(True)
        layout.addWidget(setup_hint)

        audit_hint = QLabel(
            "Lưu ý: khi OAuth consent screen còn ở trạng thái 'Testing' (mặc định), phiên đăng nhập chỉ "
            "dùng được 7 ngày rồi cần đăng nhập lại — vào Google Cloud Console, chuyển Publishing status "
            "sang 'In production' để dùng lâu dài (sẽ thấy cảnh báo 'ứng dụng chưa xác minh', bấm "
            "Advanced → Go to (tên app) là được vì đây chính là app bạn tự tạo)."
        )
        audit_hint.setObjectName("mutedHint")
        audit_hint.setWordWrap(True)
        layout.addWidget(audit_hint)

        self.connect_btn = QPushButton("Đăng nhập Google/YouTube")
        self.connect_btn.setObjectName("primaryButton")
        self.connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(self.connect_btn)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.disconnect_btn = QPushButton("Ngắt kết nối")
        self.disconnect_btn.setObjectName("linkButton")
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        layout.addWidget(self.disconnect_btn)
        layout.addStretch(1)
        arrange_cards(layout, [("Kết nối tài khoản", [0, 1, 2, 3, 4])])

    def _on_connect(self) -> None:
        settings = config.load_settings()
        client_id = settings.get("youtube_client_id", "")
        client_secret = config.get_secret("youtube_client_secret")
        if not client_id or not client_secret:
            self.log_message.emit("Vui lòng nhập YouTube (Google) Client ID/Secret trong tab Cài đặt trước.", "error")
            return

        self.connect_btn.setEnabled(False)
        self.log_message.emit("Đang bắt đầu đăng nhập Google...", "info")
        self._worker = Worker(authorize_and_get_tokens, client_id=client_id, client_secret=client_secret)
        self._worker.progress.connect(lambda msg: self.log_message.emit(msg, "info"))
        self._worker.finished.connect(self._on_connected)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_connected(self, tokens: dict) -> None:
        self.connect_btn.setEnabled(True)
        config.save_youtube_account(
            channel_title=tokens.get("channel_title", ""),
            channel_id=tokens.get("channel_id", ""),
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token", ""),
            expires_at=tokens.get("expires_at", 0),
        )
        self._refresh_status()
        self.account_changed.emit()
        self.log_message.emit("Đã kết nối YouTube thành công.", "success")

    def _on_error(self, message: str) -> None:
        self.connect_btn.setEnabled(True)
        self.log_message.emit(f"Lỗi kết nối YouTube: {message}", "error")

    def _on_disconnect(self) -> None:
        config.clear_youtube_account()
        self._refresh_status()
        self.account_changed.emit()
        self.log_message.emit("Đã ngắt kết nối YouTube.", "info")

    def _refresh_status(self) -> None:
        account = config.get_youtube_account()
        connected = bool(account.get("access_token"))
        self.disconnect_btn.setEnabled(connected)
        if connected:
            name = account.get("channel_title") or account.get("channel_id") or "(không rõ tên kênh)"
            self.status_label.setText(f"✓ Đã kết nối YouTube: {name}")
        else:
            self.status_label.setText("Chưa kết nối kênh YouTube nào.")
