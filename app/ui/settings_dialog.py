"""Trang cài đặt API và Facebook App trong cửa sổ chính."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.claude_client import ClaudeClient
from app.core.heygen_client import HeyGenClient
from app.core.grok_video_client import GrokVideoClient
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.design import arrange_cards
from app.ui.widgets.appearance_panel import AppearancePanel
from app.workers.async_worker import Worker


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Worker | None = None
        self._build_ui()
        self._load_current_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(make_page_header("⚙️ Cài đặt", "Quản lý API key. Facebook Page được quản lý riêng ở tab 'Kết nối Facebook'."))

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(7)

        self.anthropic_key_input = QLineEdit()
        self.anthropic_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        anthropic_row = self._with_test_button(self.anthropic_key_input, self._test_anthropic)
        form.addRow("Anthropic (Claude) API key:", anthropic_row)

        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        openai_row = self._with_test_button(self.openai_key_input, self._test_openai)
        form.addRow("OpenAI API key:", openai_row)

        self.heygen_key_input = QLineEdit()
        self.heygen_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        heygen_row = self._with_test_button(self.heygen_key_input, self._test_heygen)
        form.addRow("HeyGen API key:", heygen_row)

        self.grok_key_input = QLineEdit()
        self.grok_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        grok_row = self._with_test_button(self.grok_key_input, self._test_grok)
        form.addRow("Grok (xAI) API key:", grok_row)

        self.fb_app_id_input = QLineEdit()
        form.addRow("Facebook App ID (tuỳ chọn):", self.fb_app_id_input)

        self.fb_app_secret_input = QLineEdit()
        self.fb_app_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Facebook App Secret (tuỳ chọn):", self.fb_app_secret_input)

        self.tiktok_client_key_input = QLineEdit()
        form.addRow("TikTok Client Key:", self.tiktok_client_key_input)

        self.tiktok_client_secret_input = QLineEdit()
        self.tiktok_client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("TikTok Client Secret:", self.tiktok_client_secret_input)

        self.youtube_client_id_input = QLineEdit()
        form.addRow("YouTube (Google) Client ID:", self.youtube_client_id_input)

        self.youtube_client_secret_input = QLineEdit()
        self.youtube_client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("YouTube (Google) Client Secret:", self.youtube_client_secret_input)

        layout.addLayout(form)

        mongo_form = QFormLayout()
        mongo_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        mongo_form.setVerticalSpacing(7)

        self.mongo_uri_input = QLineEdit()
        self.mongo_uri_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.mongo_uri_input.setPlaceholderText("mongodb+srv://user:password@cluster.mongodb.net")
        mongo_uri_row = self._with_test_button(self.mongo_uri_input, self._test_mongo)
        mongo_form.addRow("MongoDB Atlas connection string (tuỳ chọn):", mongo_uri_row)

        self.mongo_db_input = QLineEdit()
        self.mongo_db_input.setPlaceholderText("claude_content_studio")
        mongo_form.addRow("Tên database:", self.mongo_db_input)

        mongo_hint = QLabel(
            "Để trống: lịch sử content/ảnh/video/bài đăng vẫn lưu cục bộ (SQLite) như trước, không cần MongoDB. "
            "Dán connection string hợp lệ: mọi lịch sử mới sẽ tự động ghi vào MongoDB Atlas thay vì máy này."
        )
        mongo_hint.setWordWrap(True)
        mongo_hint.setObjectName("mutedHint")
        mongo_form.addRow(mongo_hint)

        layout.addLayout(mongo_form)

        hint = QLabel(
            "Ghi chú: API key được lưu an toàn trong kho mật khẩu của hệ điều hành, không lưu dạng văn bản thuần. "
            "Facebook App ID/Secret không bắt buộc — chỉ dùng để tự động đổi User Access Token (dán ở tab "
            "'Kết nối Facebook') sang bản dài hạn. Nếu bỏ trống, kết nối vẫn hoạt động nhưng token chỉ dùng "
            "được trong ~1-2 giờ. TikTok Client Key/Secret lấy từ app bạn tạo tại developers.tiktok.com/apps — "
            "bắt buộc phải có để đăng nhập ở tab 'Kết nối TikTok'. YouTube Client ID/Secret lấy từ project tại "
            "console.cloud.google.com (loại OAuth client 'Desktop app') — bắt buộc phải có để đăng nhập ở tab "
            "'Kết nối YouTube'."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.save_btn = QPushButton("Lưu cài đặt")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self._on_save)
        actions.addWidget(self.save_btn)
        layout.addLayout(actions)
        layout.addStretch(1)
        arrange_cards(
            layout,
            [
                ("API key & Facebook App", [0, 3, 4]),
                ("Lưu trữ dữ liệu (MongoDB)", [1]),
                ("Thông tin lưu trữ", [2]),
            ],
        )
        self.appearance_panel = AppearancePanel()
        layout.insertWidget(1, self.appearance_panel)

    def _with_test_button(self, line_edit: QLineEdit, handler) -> QWidget:
        wrapper = QWidget()
        h = QVBoxLayout(wrapper)
        h.setContentsMargins(0, 0, 0, 0)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(line_edit)
        test_btn = QPushButton("Kiểm tra")
        test_btn.setObjectName("linkButton")
        test_btn.clicked.connect(handler)
        row_layout.addWidget(test_btn)
        h.addWidget(row)
        return wrapper

    def _load_current_values(self) -> None:
        self.anthropic_key_input.setText(config.get_secret("anthropic_api_key"))
        self.openai_key_input.setText(config.get_secret("openai_api_key"))
        self.heygen_key_input.setText(config.get_secret("heygen_api_key"))
        self.grok_key_input.setText(config.get_secret("grok_api_key"))
        settings = config.load_settings()
        self.fb_app_id_input.setText(settings.get("facebook_app_id", ""))
        self.fb_app_secret_input.setText(config.get_secret("facebook_app_secret"))
        self.tiktok_client_key_input.setText(settings.get("tiktok_client_key", ""))
        self.tiktok_client_secret_input.setText(config.get_secret("tiktok_client_secret"))
        self.youtube_client_id_input.setText(settings.get("youtube_client_id", ""))
        self.youtube_client_secret_input.setText(config.get_secret("youtube_client_secret"))
        self.mongo_uri_input.setText(config.get_secret("mongodb_uri"))
        self.mongo_db_input.setText(settings.get("mongodb_database", "claude_content_studio"))

    def _test_anthropic(self) -> None:
        try:
            client = ClaudeClient(self.anthropic_key_input.text().strip())
            client.generate_post("kiểm tra kết nối", length="ngắn (10-20 từ)", include_hashtags=False)
            self.status_label.setText("Anthropic: kết nối OK.")
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"Anthropic lỗi: {exc}")

    def _test_openai(self) -> None:
        key = self.openai_key_input.text().strip()
        if not key:
            self.status_label.setText("OpenAI: thiếu API key.")
            return
        try:
            from openai import OpenAI

            OpenAI(api_key=key).models.list()
            self.status_label.setText("OpenAI: kết nối OK.")
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"OpenAI lỗi: {exc}")

    def _test_heygen(self) -> None:
        try:
            client = HeyGenClient(self.heygen_key_input.text().strip())
            avatars = client.list_avatars()
            self.status_label.setText(f"HeyGen: kết nối OK ({len(avatars)} avatar khả dụng).")
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"HeyGen lỗi: {exc}")

    def _test_grok(self) -> None:
        try:
            client = GrokVideoClient(self.grok_key_input.text().strip())
            client.list_models()
            self.status_label.setText("Grok (xAI): kết nối OK.")
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"Grok (xAI) lỗi: {exc}")

    def _test_mongo(self) -> None:
        uri = self.mongo_uri_input.text().strip()
        if not uri:
            self.status_label.setText("MongoDB: chưa nhập connection string.")
            return
        try:
            from pymongo import MongoClient

            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            try:
                client.admin.command("ping")
            finally:
                client.close()
            db_name = self.mongo_db_input.text().strip() or "claude_content_studio"
            self.status_label.setText(f"MongoDB: kết nối OK (database: {db_name}).")
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"MongoDB lỗi: {exc}")

    def _on_save(self) -> None:
        config.set_secret("anthropic_api_key", self.anthropic_key_input.text().strip())
        config.set_secret("openai_api_key", self.openai_key_input.text().strip())
        config.set_secret("heygen_api_key", self.heygen_key_input.text().strip())
        config.set_secret("grok_api_key", self.grok_key_input.text().strip())
        config.set_secret("facebook_app_secret", self.fb_app_secret_input.text().strip())
        config.set_secret("tiktok_client_secret", self.tiktok_client_secret_input.text().strip())
        config.set_secret("youtube_client_secret", self.youtube_client_secret_input.text().strip())
        config.set_secret("mongodb_uri", self.mongo_uri_input.text().strip())

        settings = config.load_settings()
        settings["facebook_app_id"] = self.fb_app_id_input.text().strip()
        settings["tiktok_client_key"] = self.tiktok_client_key_input.text().strip()
        settings["youtube_client_id"] = self.youtube_client_id_input.text().strip()
        settings["mongodb_database"] = self.mongo_db_input.text().strip() or "claude_content_studio"
        config.save_settings(settings)

        self.status_label.setText("✓ Cấu hình đã được lưu an toàn.")
