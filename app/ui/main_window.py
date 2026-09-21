"""Main application window: left sidebar nav (grouped under section headers) + stacked
pages + shared log console."""
from __future__ import annotations

from PySide6.QtCore import QDate, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QLineEdit,
    QMenu,
    QCompleter,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.windows_acrylic import disable_window_blur, enable_window_blur
from app.ui.theme import appearance_options, apply_theme, is_light_appearance, native_glass_tint
from app.storage import history_store
from app.ui.automation_tab import AutomationTab
from app.ui.automation_settings_dialog import AutomationSettingsTab
from app.ui.content_tab import ContentTab
from app.ui.archive_tab import ArchiveTab
from app.ui.dashboard_tab import DashboardTab
from app.ui.facebook_connect_tab import FacebookConnectTab
from app.ui.facebook_tab import FacebookTab
from app.ui.facebook_schedule_tab import FacebookScheduleTab
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
from app.ui.widgets.glass_chrome import GlassTitleBar
from app.ui.widgets.liquid_glass import apply_button_elevation

# Each entry is either ("header", label) or ("item", label, key).
NAV_ENTRIES = [
    ("item", "Dashboard", "dashboard"),
    ("header", "CÔNG CỤ"),
    ("item", "📝  Viết Content", "content"),
    ("item", "Kho bài viết đã đăng", "archive"),
    ("item", "🖼️  Tạo Ảnh", "image"),
    ("item", "🎬  Tạo Video", "video"),
    ("item", "📚  Bộ sưu tập", "gallery"),
    ("item", "📤  Đăng Facebook", "facebook"),
    ("item", "Lịch đăng Facebook", "facebook_schedule"),
    ("item", "🔗  Kết nối Facebook", "facebook_connect"),
    ("item", "🎵  Đăng TikTok", "tiktok"),
    ("item", "🔗  Kết nối TikTok", "tiktok_connect"),
    ("item", "🎥  Đăng YouTube", "youtube"),
    ("item", "🔗  Kết nối YouTube", "youtube_connect"),
    ("item", "🚀  Tự động hoá", "automation"),
    ("item", "📋  Nhật ký hoạt động", "logs"),
]


NAV_GROUPS = [
    ("overview", "Tổng quan", ["dashboard", "gallery"]),
    ("creation", "Sáng tạo nội dung", ["content", "image", "video", "archive"]),
    ("social", "Mạng xã hội", ["facebook", "tiktok", "youtube"]),
    ("connections", "Kết nối", ["facebook_connect", "tiktok_connect", "youtube_connect"]),
    ("management", "Quản lý", ["facebook_schedule", "automation", "logs"]),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Claude Content Studio")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.resize(1240, 840)
        self.setMinimumSize(980, 680)

        config.migrate_legacy_facebook_config()
        history_store.init_db()

        self.dashboard_tab = DashboardTab()
        self.content_tab = ContentTab()
        self.archive_tab = ArchiveTab()
        self.image_tab = ImageTab()
        self.video_tab = VideoTab()
        self.gallery_tab = GalleryTab()
        self.facebook_tab = FacebookTab()
        self.facebook_schedule_tab = FacebookScheduleTab()
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
        self._appearance = appearance_options(config.load_settings())
        self.apply_appearance(self._appearance)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralArea")
        central.setProperty("glassFallback", True)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(20, 18, 20, 20)
        root_layout.setSpacing(14)
        root_layout.addWidget(GlassTitleBar(self))
        body = QHBoxLayout()
        body.setSpacing(18)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_content_area(), 1)
        root_layout.addLayout(body, 1)

        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(64)
        self._sidebar_preferred = config.load_settings().get("sidebar_expanded", True) is not False
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(4)
        self.group_btn = self._icon_button("group", "Thu gọn / mở nhóm chức năng")
        self.group_btn.setCheckable(True)
        self.group_btn.setChecked(True)
        layout.addWidget(self.group_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)
        self.nav_group = QWidget()
        nav_layout = QVBoxLayout(self.nav_group)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(3)
        self.nav_buttons = {}
        self.nav_group_headers = {}
        self.nav_group_widgets = {}
        self.nav_key_group = {}
        saved_groups = config.load_settings().get("sidebar_groups", {})
        if not isinstance(saved_groups, dict):
            saved_groups = {}
        labels = {entry[2]: entry[1].split("  ", 1)[-1] for entry in NAV_ENTRIES if entry[0] == "item"}
        for group_key, title, keys in NAV_GROUPS:
            section = QWidget()
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(0, 2, 0, 2)
            section_layout.setSpacing(3)
            header = QPushButton()
            header.setObjectName("navGroupHeader")
            header.setCheckable(True)
            header.setChecked(saved_groups.get(group_key, True) is not False)
            header.setFixedSize(192, 28)
            header.setAccessibleName(title)
            self.nav_group_headers[group_key] = header
            section_layout.addWidget(header, 0, Qt.AlignmentFlag.AlignHCenter)
            items = QWidget()
            items_layout = QVBoxLayout(items)
            items_layout.setContentsMargins(0, 0, 0, 0)
            items_layout.setSpacing(3)
            for key in keys:
                button = self._icon_button(key, labels[key])
                button.setCheckable(True)
                button.clicked.connect(lambda checked=False, k=key: self._show_page(k))
                self.nav_buttons[key] = button
                self.nav_key_group[key] = group_key
                items_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            self.nav_group_widgets[group_key] = items
            section_layout.addWidget(items)
            header.toggled.connect(lambda opened, k=group_key: self._toggle_nav_group(k, opened))
            nav_layout.addWidget(section)
        nav_layout.addStretch(1)
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setObjectName("navScroll")
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_scroll.setMinimumHeight(60)
        self.nav_scroll.setWidget(self.nav_group)
        layout.addWidget(self.nav_scroll, 1)
        self.group_btn.toggled.connect(self._toggle_sidebar)
        self.settings_btn = self._icon_button("settings", "Cài đặt")
        self.settings_btn.setCheckable(True)
        self.settings_btn.clicked.connect(lambda: self._show_page("settings"))
        layout.addWidget(self.settings_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self.nav_buttons["dashboard"].setChecked(True)
        self.sidebar = sidebar
        self._sync_sidebar()
        return sidebar

    def _toggle_sidebar(self, expanded: bool) -> None:
        self._sidebar_preferred = expanded
        if expanded and self.width() < 1140:
            self.resize(1140, self.height())
        settings = config.load_settings()
        settings["sidebar_expanded"] = expanded
        config.save_settings(settings)
        self._sync_sidebar()

    def _sync_sidebar(self) -> None:
        expanded = self._sidebar_preferred and self.width() >= 1140
        if getattr(self, "_sidebar_expanded", None) == expanded:
            return
        self._sidebar_expanded = expanded
        self.sidebar.setFixedWidth(224 if expanded else 64)
        self.group_btn.blockSignals(True)
        self.group_btn.setChecked(expanded)
        self.group_btn.blockSignals(False)
        buttons = [self.group_btn, *self.nav_buttons.values(), self.settings_btn]
        for button in buttons:
            button.setProperty("sidebarNav", True)
            button.setProperty("expanded", expanded)
            button.setText(("Chức năng" if button is self.group_btn else button.toolTip()) if expanded else "")
            button.setFixedSize(192 if expanded else 34, 34)
            button.style().unpolish(button)
            button.style().polish(button)
        self.group_btn.setToolTip("Thu gọn sidebar" if expanded else "Mở rộng sidebar")
        self._sync_nav_groups()

    def _sync_nav_groups(self) -> None:
        for key, title, _ in NAV_GROUPS:
            header = self.nav_group_headers[key]
            opened = header.isChecked()
            header.setText(("▾ " if opened else "▸ ") + title)
            header.setToolTip(("Thu gọn " if opened else "Mở nhóm ") + title)
            header.setVisible(self._sidebar_expanded)
            self.nav_group_widgets[key].setVisible(not self._sidebar_expanded or opened)

    def _toggle_nav_group(self, key: str, opened: bool) -> None:
        self._sync_nav_groups()
        settings = config.load_settings()
        groups = settings.get("sidebar_groups", {})
        groups = dict(groups) if isinstance(groups, dict) else {}
        groups[key] = opened
        settings["sidebar_groups"] = groups
        config.save_settings(settings)

    def _icon_button(self, key: str, label: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("railButton")
        button.setProperty("iconName", key)
        button.setIcon(line_icon(key))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(34, 34)
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
        add_page("archive", self.archive_tab)
        add_page("image", self.image_tab)
        add_page("video", self.video_tab)
        add_page("gallery", self.gallery_tab)
        add_page("facebook", self.facebook_tab)
        add_page("facebook_schedule", self.facebook_schedule_tab)
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
        wrapper_layout.setContentsMargins(20, 16, 20, 20)
        wrapper_layout.setSpacing(18)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(7)
        self.page_labels = {entry[2]: entry[1].split("  ", 1)[-1] for entry in NAV_ENTRIES if entry[0] == "item"}
        self.page_labels.update(settings="Cài đặt", automation_settings="Cài đặt tự động hoá")
        self.tool_search = QLineEdit()
        self.tool_search.setObjectName("toolSearch")
        self.tool_search.setPlaceholderText("Tìm công cụ…")
        self.tool_search.setFixedWidth(158)
        self.tool_search.setClearButtonEnabled(True)
        self.search_action = self.tool_search.addAction(line_icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        completer = QCompleter(list(self.page_labels.values()), self.tool_search)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.tool_search.setCompleter(completer)
        completer.popup().setObjectName("toolSearchPopup")
        completer.activated.connect(self._open_search_result)
        self.tool_search.returnPressed.connect(lambda: self._open_search_result(self.tool_search.text()))
        toolbar.addWidget(self.tool_search)
        self.shortcut_buttons = {}
        for key, label in [("dashboard", "Tổng quan"), ("content", "Content"), ("image", "Hình ảnh"), ("video", "Video")]:
            button = QPushButton(label)
            button.setObjectName("topTab")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, k=key: self._show_page(k))
            toolbar.addWidget(button)
            self.shortcut_buttons[key] = button
        self.more_button = QPushButton("Thêm")
        self.more_button.setObjectName("topTab")
        self.more_button.setCheckable(True)
        menu = QMenu(self.more_button)
        for key, label in self.page_labels.items():
            if key not in self.shortcut_buttons:
                action = menu.addAction(line_icon(key if key != "automation_settings" else "settings"), label)
                action.setData(key)
                action.triggered.connect(lambda checked=False, k=key: self._show_page(k))
        self.more_button.setMenu(menu)
        toolbar.addWidget(self.more_button)
        toolbar.addStretch(1)
        self.date_label = QLabel()
        self.date_label.setObjectName("toolbarDate")
        self._refresh_date()
        self.date_timer = QTimer(self)
        self.date_timer.timeout.connect(self._refresh_date)
        self.date_timer.start(60000)
        toolbar.addWidget(self.date_label)
        logs_button = self._icon_button("logs", "Nhật ký hoạt động")
        logs_button.clicked.connect(lambda: self._show_page("logs"))
        toolbar.addWidget(logs_button)
        profile = self._icon_button("user", "Cài đặt tài khoản và ứng dụng")
        profile.setObjectName("profileButton")
        profile.clicked.connect(lambda: self._show_page("settings"))
        toolbar.addWidget(profile)
        wrapper_layout.addLayout(toolbar)
        wrapper_layout.addWidget(self.stack, 1)
        return wrapper

    def _refresh_date(self) -> None:
        self.date_label.setText(QDate.currentDate().toString("dd / MM"))

    def _open_search_result(self, text: str) -> None:
        query = text.strip().casefold()
        if not query:
            return
        matches = [key for key, label in self.page_labels.items() if query == label.casefold()]
        if not matches:
            matches = [key for key, label in self.page_labels.items() if query in label.casefold()]
        if matches:
            self._show_page(matches[0])
            self.tool_search.clear()

    def _show_page(self, key: str) -> None:
        group = self.nav_key_group.get(key)
        if group and self._sidebar_expanded:
            self.nav_group_headers[group].setChecked(True)
        self.stack.setCurrentIndex(self._page_stack_index[key])
        if key == "dashboard":
            self.dashboard_tab.refresh()
        elif key == "gallery":
            self.gallery_tab.refresh()
        elif key == "archive":
            self.archive_tab.refresh()
        elif key == "facebook_schedule":
            self.facebook_schedule_tab.refresh()
        for name, button in {**self.nav_buttons, "settings": self.settings_btn}.items():
            active = name == key or (name == "settings" and key == "automation_settings")
            button.setChecked(active)
            crystal = QApplication.instance().property("glassStyle") == "crystal"
            color = ("#167d9e" if active else "#40586b") if crystal else ("#ffffff" if active else "#deded9")
            button.setIcon(line_icon(name, color))
        self.more_button.setChecked(key not in self.shortcut_buttons)
        for name, button in self.shortcut_buttons.items():
            button.setChecked(name == key)

    def _reuse_archived_content(self, destination: str, topic: str, text: str) -> None:
        if destination == "content":
            if not self.content_tab.load_archived_content(topic, text):
                return
        elif destination == "image":
            self.image_tab.set_context_from_content(text)
        elif destination == "video":
            self.video_tab.set_context_from_content(text)
        elif destination == "facebook":
            self.facebook_tab.set_message(text)
        else:
            return
        self._show_page(destination)

    def _wire_signals(self) -> None:
        self.settings_tab.appearance_panel.appearance_changed.connect(self.apply_appearance)
        self.dashboard_tab.page_requested.connect(self._show_page)
        self.automation_tab.settings_requested.connect(lambda: self._show_page("automation_settings"))
        self.content_tab.use_for_image.connect(self.image_tab.set_context_from_content)
        self.content_tab.use_for_video.connect(self.video_tab.set_context_from_content)
        self.content_tab.use_for_post.connect(self.facebook_tab.set_message)
        self.archive_tab.reuse_requested.connect(self._reuse_archived_content)
        self.facebook_tab.schedules_requested.connect(lambda: self._show_page("facebook_schedule"))

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
            self.archive_tab,
            self.image_tab,
            self.video_tab,
            self.gallery_tab,
            self.facebook_tab,
            self.facebook_schedule_tab,
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

    def apply_appearance(self, options) -> None:
        self._appearance = appearance_options(options)
        app = QApplication.instance()
        if app:
            apply_theme(app, self._appearance)
        apply_button_elevation(self)
        self._refresh_theme_icons()
        self._refresh_glass()

    def _refresh_theme_icons(self) -> None:
        crystal = is_light_appearance(self._appearance)
        for button in self.findChildren(QPushButton):
            name = button.property("iconName")
            if name:
                color = ("#167d9e" if button.isChecked() else "#40586b") if crystal else ("#ffffff" if button.isChecked() else "#deded9")
                if button.objectName() == "quickTool":
                    colors = {"content": "#b56832", "image": "#19799b", "video": "#6573a5"} if crystal else {"content": "#e4bd9a", "image": "#a8cde2", "video": "#c5b3db"}
                    color = colors[name]
                button.setIcon(line_icon(name, color))
        self.search_action.setIcon(line_icon("search", "#40586b" if crystal else "#deded9"))
        for action in self.more_button.menu().actions():
            name = action.data()
            action.setIcon(line_icon("settings" if name == "automation_settings" else name, "#40586b" if crystal else "#deded9"))

    def _refresh_glass(self) -> None:
        app = QApplication.instance()
        if self.isVisible() and app and app.platformName() == "windows":
            # Native Acrylic also covers empty gutters; enable it only by opt-in.
            if self._appearance["glass_blur"]:
                enable_window_blur(int(self.winId()), *native_glass_tint(self._appearance))
            else:
                disable_window_blur(int(self.winId()))
        central = self.centralWidget()
        central.setProperty("glassFallback", True)
        central.style().unpolish(central)
        central.style().polish(central)
        central.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._refresh_glass)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "_appearance"):
            from PySide6.QtCore import QEvent
            if event.type() == QEvent.Type.WindowStateChange:
                QTimer.singleShot(0, self._refresh_glass)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            self._sync_sidebar()
        if hasattr(self, "toast") and self.toast.isVisible():
            self.toast.show_message(self.toast.message.text(), self.toast.property("level") or "info")
