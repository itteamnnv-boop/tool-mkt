"""Main application window: left sidebar nav (grouped under section headers) + stacked
pages + shared log console."""
from __future__ import annotations

from PySide6.QtCore import QDate, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.storage import history_store
from app.ui.automation_tab import AutomationTab
from app.ui.automation_settings_dialog import AutomationSettingsTab
from app.ui.content_tab import ContentTab
from app.ui.dashboard_tab import DashboardTab
from app.ui.facebook_connect_tab import FacebookConnectTab
from app.ui.facebook_tab import FacebookTab
from app.ui.gallery_tab import GalleryTab
from app.ui.image_tab import ImageTab
from app.ui.log_tab import LogTab
from app.ui.settings_dialog import SettingsTab
from app.ui.tiktok_connect_tab import TikTokConnectTab
from app.ui.tiktok_tab import TikTokTab
from app.ui.video_tab import VideoTab
from app.ui.youtube_connect_tab import YouTubeConnectTab
from app.ui.youtube_tab import YouTubeTab
from app.ui.widgets.design import compact_labels, line_icon
from app.ui.widgets.toast import Toast

# Each entry is either ("header", label) or ("item", label, key).
NAV_ENTRIES = [
    ("item", "Dashboard", "dashboard"),
    ("header", "CÔNG CỤ"),
    ("item", "📝  Viết Content", "content"),
    ("item", "🖼️  Tạo Ảnh", "image"),
    ("item", "🎬  Tạo Video", "video"),
    ("item", "📚  Bộ sưu tập", "gallery"),
    ("item", "📤  Đăng Facebook", "facebook"),
    ("item", "🔗  Kết nối Facebook", "facebook_connect"),
    ("item", "🎵  Đăng TikTok", "tiktok"),
    ("item", "🔗  Kết nối TikTok", "tiktok_connect"),
    ("item", "🎥  Đăng YouTube", "youtube"),
    ("item", "🔗  Kết nối YouTube", "youtube_connect"),
    ("item", "🚀  Tự động hoá", "automation"),
    ("item", "📋  Nhật ký hoạt động", "logs"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(1240, 840)
        self.setMinimumSize(980, 680)

        config.migrate_legacy_facebook_config()
        history_store.init_db()

        self.dashboard_tab = DashboardTab()
        self.content_tab = ContentTab()
        self.image_tab = ImageTab()
        self.video_tab = VideoTab()
        self.gallery_tab = GalleryTab()
        self.facebook_tab = FacebookTab()
        self.facebook_connect_tab = FacebookConnectTab()
        self.tiktok_tab = TikTokTab()
        self.tiktok_connect_tab = TikTokConnectTab()
        self.youtube_tab = YouTubeTab()
        self.youtube_connect_tab = YouTubeConnectTab()
        self.automation_tab = AutomationTab()
        self.log_tab = LogTab()
        self.log_console = self.log_tab.console
        self.settings_tab = SettingsTab()
        self.automation_settings_tab = AutomationSettingsTab()

        self._page_stack_index: dict[str, int] = {}
        self._build_ui()
        self.toast = Toast(self)
        self._wire_signals()
        self._show_page("dashboard")

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralArea")
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_content_area(), stretch=1)

        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(82)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(8)
        self.group_btn = self._icon_button("group", "Thu gọn / mở nhóm chức năng")
        self.group_btn.setCheckable(True)
        self.group_btn.setChecked(True)
        layout.addWidget(self.group_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(20)
        self.nav_group = QWidget()
        nav_layout = QVBoxLayout(self.nav_group)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)
        self.nav_buttons = {}
        for kind, label, *keys in NAV_ENTRIES:
            if kind != "item":
                continue
            key = keys[0]
            button = self._icon_button(key, label.split("  ", 1)[-1])
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, k=key: self._show_page(k))
            self.nav_buttons[key] = button
            nav_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.nav_group)
        self.group_btn.toggled.connect(self.nav_group.setVisible)
        layout.addStretch(1)
        self.settings_btn = self._icon_button("settings", "Cài đặt")
        self.settings_btn.setCheckable(True)
        self.settings_btn.clicked.connect(lambda: self._show_page("settings"))
        layout.addWidget(self.settings_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self.nav_buttons["dashboard"].setChecked(True)
        return sidebar

    def _icon_button(self, key: str, label: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("railButton")
        button.setIcon(line_icon(key))
        button.setIconSize(QSize(24, 24))
        button.setFixedSize(46, 46)
        button.setToolTip(label)
        button.setAccessibleName(label)
        return button

    def _build_content_area(self) -> QWidget:
        self.stack = QStackedWidget()

        def add_page(key: str, widget: QWidget) -> None:
            compact_labels(widget)
            scroll = QScrollArea()
            scroll.setObjectName("pageScroll")
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            self._page_stack_index[key] = self.stack.addWidget(scroll)

        add_page("dashboard", self.dashboard_tab)
        add_page("content", self.content_tab)
        add_page("image", self.image_tab)
        add_page("video", self.video_tab)
        add_page("gallery", self.gallery_tab)
        add_page("facebook", self.facebook_tab)
        add_page("facebook_connect", self.facebook_connect_tab)
        add_page("tiktok", self.tiktok_tab)
        add_page("tiktok_connect", self.tiktok_connect_tab)
        add_page("youtube", self.youtube_tab)
        add_page("youtube_connect", self.youtube_connect_tab)
        add_page("automation", self.automation_tab)
        add_page("logs", self.log_tab)
        add_page("settings", self.settings_tab)
        add_page("automation_settings", self.automation_settings_tab)

        wrapper = QWidget()
        wrapper.setObjectName("contentShell")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(28, 20, 28, 24)
        wrapper_layout.setSpacing(24)
        toolbar = QHBoxLayout()
        context = QLabel("Không gian làm việc\nPhiên cục bộ")
        context.setObjectName("workspaceBadge")
        toolbar.addWidget(context)
        toolbar.addStretch(1)
        self.date_label = QLabel()
        self.date_label.setObjectName("toolbarDate")
        self._refresh_date()
        self.date_timer = QTimer(self)
        self.date_timer.timeout.connect(self._refresh_date)
        self.date_timer.start(60000)
        toolbar.addWidget(self.date_label)
        toolbar.addStretch(1)
        logs_button = self._icon_button("logs", "Nhật ký hoạt động")
        logs_button.clicked.connect(lambda: self._show_page("logs"))
        toolbar.addWidget(logs_button)
        wrapper_layout.addLayout(toolbar)
        wrapper_layout.addWidget(self.stack, 1)
        shortcuts = QHBoxLayout()
        shortcuts.setSpacing(14)
        self.shortcut_buttons = {}
        for number, (key, label) in enumerate([
            ("content", "Viết Content"), ("image", "Tạo Ảnh"), ("video", "Tạo Video"),
            ("facebook", "Đăng Facebook"), ("automation", "Tự động hoá"),
        ], 1):
            button = QPushButton(f"{number:02d}\n\n{label}")
            button.setObjectName("shortcutCard")
            button.setCheckable(True)
            button.setFixedHeight(98)
            button.clicked.connect(lambda checked=False, k=key: self._show_page(k))
            shortcuts.addWidget(button, 1)
            self.shortcut_buttons[key] = button
        wrapper_layout.addLayout(shortcuts)
        return wrapper

    def _refresh_date(self) -> None:
        self.date_label.setText(QDate.currentDate().toString("dd / MM\nyyyy"))

    def _show_page(self, key: str) -> None:
        self.stack.setCurrentIndex(self._page_stack_index[key])
        if key == "dashboard":
            self.dashboard_tab.refresh()
        elif key == "gallery":
            self.gallery_tab.refresh()
        for name, button in {**self.nav_buttons, "settings": self.settings_btn}.items():
            active = name == key or (name == "settings" and key == "automation_settings")
            button.setChecked(active)
            button.setIcon(line_icon(name, "#2dbac5" if active else "#89949e"))
        for name, button in self.shortcut_buttons.items():
            button.setChecked(name == key)

    def _wire_signals(self) -> None:
        self.automation_tab.settings_requested.connect(lambda: self._show_page("automation_settings"))
        self.content_tab.use_for_image.connect(self.image_tab.set_context_from_content)
        self.content_tab.use_for_video.connect(self.video_tab.set_context_from_content)
        self.content_tab.use_for_post.connect(self.facebook_tab.set_message)

        self.image_tab.image_generated.connect(self.facebook_tab.set_image_path)
        self.image_tab.use_for_video.connect(self.video_tab.set_reference_image)
        self.video_tab.video_generated.connect(self.facebook_tab.set_video_path)
        self.video_tab.video_generated.connect(self.tiktok_tab.set_video_path)
        self.video_tab.video_generated.connect(self.youtube_tab.set_video_path)

        self.gallery_tab.use_for_post_image.connect(self.facebook_tab.set_image_path)
        self.gallery_tab.use_for_post_video.connect(self.facebook_tab.set_video_path)
        self.gallery_tab.use_for_video_material.connect(self.video_tab.set_reference_image)
        self.gallery_tab.use_for_tiktok_video.connect(self.tiktok_tab.set_video_path)
        self.gallery_tab.use_for_youtube_video.connect(self.youtube_tab.set_video_path)

        self.facebook_connect_tab.pages_changed.connect(self.facebook_tab.pages_selector.refresh)
        self.facebook_connect_tab.pages_changed.connect(self.automation_tab.pages_selector.refresh)

        for tab in (
            self.content_tab,
            self.image_tab,
            self.video_tab,
            self.gallery_tab,
            self.facebook_tab,
            self.facebook_connect_tab,
            self.tiktok_tab,
            self.tiktok_connect_tab,
            self.youtube_tab,
            self.youtube_connect_tab,
            self.automation_tab,
            self.automation_settings_tab,
        ):
            tab.log_message.connect(self._handle_log_message)

    def _handle_log_message(self, message: str, level: str) -> None:
        """Keep the activity log and visible feedback in sync."""
        self.log_console.log(message, level)
        self.toast.show_message(message, level)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "toast") and self.toast.isVisible():
            self.toast.show_message(self.toast.message.text(), self.toast.property("level") or "info")
