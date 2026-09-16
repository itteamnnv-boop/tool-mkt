"""Tab: connect a TikTok account via OAuth (desktop PKCE flow), then manage the connection."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from app import config
from app.core.tiktok_client import REDIRECT_URI, authorize_and_get_tokens
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.workers.async_worker import Worker


class TikTokConnectTab(QWidget):
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
                "🔗 Kết nối TikTok",
                "Đăng nhập TikTok bằng trình duyệt (OAuth) để lấy quyền đăng video. Chỉ cần làm 1 lần.",
            )
        )

        setup_hint = QLabel(
            "1. Tạo app tại developers.tiktok.com/apps → thêm sản phẩm 'Login Kit' và 'Content Posting API'.\n"
            "2. Trong Login Kit, đăng ký chính xác Redirect URI bên dưới.\n"
            "3. Sang tab Cài đặt, dán TikTok Client Key/Client Secret của app đó.\n"
            "4. Quay lại đây, bấm 'Đăng nhập TikTok'."
        )
        setup_hint.setWordWrap(True)
        layout.addWidget(setup_hint)

        redirect_row = QHBoxLayout()
        redirect_row.addWidget(QLabel("Redirect URI:"))
        self.redirect_uri_display = QLineEdit(REDIRECT_URI)
        self.redirect_uri_display.setReadOnly(True)
        redirect_row.addWidget(self.redirect_uri_display, 1)
        layout.addLayout(redirect_row)

        audit_hint = QLabel(
            "Lưu ý: cho đến khi app TikTok của bạn được TikTok DUYỆT (audit), mọi video đăng qua API "
            "chỉ hiển thị ở chế độ riêng tư (Chỉ mình tôi), bất kể chọn quyền riêng tư nào lúc đăng."
        )
        audit_hint.setObjectName("mutedHint")
        audit_hint.setWordWrap(True)
        layout.addWidget(audit_hint)

        self.connect_btn = QPushButton("Đăng nhập TikTok")
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
        arrange_cards(layout, [("Kết nối tài khoản", [0, 1, 2, 3, 4, 5])])

    def _on_connect(self) -> None:
        settings = config.load_settings()
        client_key = settings.get("tiktok_client_key", "")
        client_secret = config.get_secret("tiktok_client_secret")
        if not client_key or not client_secret:
            self.log_message.emit("Vui lòng nhập TikTok Client Key/Secret trong tab Cài đặt trước.", "error")
            return

        self.connect_btn.setEnabled(False)
        self.log_message.emit("Đang bắt đầu đăng nhập TikTok...", "info")
        self._worker = Worker(authorize_and_get_tokens, client_key=client_key, client_secret=client_secret)
        self._worker.progress.connect(lambda msg: self.log_message.emit(msg, "info"))
        self._worker.finished.connect(self._on_connected)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_connected(self, tokens: dict) -> None:
        self.connect_btn.setEnabled(True)
        config.save_tiktok_account(
            display_name=tokens.get("display_name", ""),
            open_id=tokens.get("open_id", ""),
            avatar_url=tokens.get("avatar_url", ""),
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token", ""),
            expires_at=tokens.get("expires_at", 0),
        )
        self._refresh_status()
        self.account_changed.emit()
        self.log_message.emit("Đã kết nối TikTok thành công.", "success")

    def _on_error(self, message: str) -> None:
        self.connect_btn.setEnabled(True)
        self.log_message.emit(f"Lỗi kết nối TikTok: {message}", "error")

    def _on_disconnect(self) -> None:
        config.clear_tiktok_account()
        self._refresh_status()
        self.account_changed.emit()
        self.log_message.emit("Đã ngắt kết nối TikTok.", "info")

    def _refresh_status(self) -> None:
        account = config.get_tiktok_account()
        connected = bool(account.get("access_token"))
        self.disconnect_btn.setEnabled(connected)
        if connected:
            name = account.get("display_name") or account.get("open_id") or "(không rõ tên)"
            self.status_label.setText(f"✓ Đã kết nối TikTok: {name}")
        else:
            self.status_label.setText("Chưa kết nối tài khoản TikTok nào.")
