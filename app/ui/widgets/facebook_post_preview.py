"""Local Facebook-style post preview; never publishes or fetches account data."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from app.ui.widgets.media_preview import MediaPreview
from app.ui.widgets.design import line_icon


class PhoneView(QGraphicsView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class FacebookPostPreview(QWidget):
    height_changed = Signal(int)
    SCREEN_WIDTH = 390
    SCREEN_HEIGHT = 844
    BEZEL = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setStyleSheet("""
            * { font-family: "Arial"; }
            QScrollArea { background: transparent; border: none; }
            QWidget#phoneStage { background: transparent; }
            QFrame#phoneShell { background: #181d27; border: 1px solid #414b5b; border-radius: 34px; }
            QFrame#phoneScreen { background: #fff; border: none; border-radius: 26px; }
            QFrame#phoneScreen QLabel { background: transparent; border: none; color: #1c1e21; }
            QFrame#phoneScreen QLabel#phoneClock { font-size: 12px; font-weight: bold; }
            QFrame#phoneScreen QLabel#phoneNotch { background: #181d27; border-bottom-left-radius: 16px; border-bottom-right-radius: 16px; }
            QFrame#phoneScreen QLabel#facebookWordmark { color: #1877f2; font-size: 25px; font-weight: bold; }
            QFrame#phoneScreen QLabel#facebookToolbar { color: #1877f2; font-size: 20px; border-bottom: 1px solid #e4e6eb; padding-bottom: 8px; }
            QFrame#phoneScreen QLabel#phoneHome { background: #181d27; border-radius: 2px; }
            QLabel#previewNote { color: #7d8797; font-size: 11px; background: transparent; border: none; }
            QScrollArea#phoneFeedScroll, QWidget#facebookFeed { background: #f0f2f5; border: none; }
            QScrollBar:vertical { width: 4px; background: #f0f2f5; }
            QScrollBar::handle:vertical { background: #ccd0d5; border-radius: 2px; min-height: 24px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QFrame#facebookPost { background: white; border: none; border-radius: 0px; }
            QFrame#facebookPost QLabel { color: #050505; background: transparent; border: none; font-size: 14px; }
            QFrame#facebookPost QLabel#facebookMeta { color: #65676b; font-size: 12px; }
            QFrame#facebookPost QLabel#facebookAvatar { background: #1877f2; color: white; border-radius: 20px; font-weight: bold; }
            QFrame#facebookPost QLabel#facebookPage { font-weight: bold; }
            QFrame#facebookPost QLabel#facebookActions { color: #65676b; border-top: 1px solid #e4e6eb; padding-top: 12px; font-weight: bold; }
        """)
        stage_layout = QVBoxLayout(self)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(0)
        self.phone = QFrame()
        self.phone.setObjectName("phoneShell")
        self.phone.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.phone.setFixedSize(self.SCREEN_WIDTH + 2 * self.BEZEL, self.SCREEN_HEIGHT + 2 * self.BEZEL)
        self.phone.setStyleSheet(self.styleSheet())
        shell = QVBoxLayout(self.phone)
        shell.setContentsMargins(self.BEZEL, self.BEZEL, self.BEZEL, self.BEZEL)
        self.screen = screen = QFrame()
        screen.setObjectName("phoneScreen")
        screen.setFixedSize(self.SCREEN_WIDTH, self.SCREEN_HEIGHT)
        shell.addWidget(screen)
        screen_layout = QVBoxLayout(screen)
        screen_layout.setContentsMargins(0, 0, 0, 8)
        screen_layout.setSpacing(0)
        status = QHBoxLayout()
        status.setContentsMargins(18, 0, 18, 0)
        clock = QLabel("9:41")
        clock.setObjectName("phoneClock")
        status.addWidget(clock)
        status.addStretch(1)
        notch = QLabel()
        notch.setObjectName("phoneNotch")
        notch.setFixedSize(170, 30)
        status.addWidget(notch, 0, Qt.AlignmentFlag.AlignTop)
        status.addStretch(1)
        status.addWidget(QLabel("4G"))
        status_bar = QWidget()
        status_bar.setFixedHeight(44)
        status_bar.setLayout(status)
        screen_layout.addWidget(status_bar)
        app_header = QHBoxLayout()
        app_header.setContentsMargins(12, 4, 12, 8)
        wordmark = QLabel("facebook")
        wordmark.setObjectName("facebookWordmark")
        app_header.addWidget(wordmark, 1)
        for icon_name in ("search", "group"):
            icon = QLabel()
            icon.setPixmap(line_icon(icon_name, "#1c1e21").pixmap(18, 18))
            app_header.addWidget(icon)
        screen_layout.addLayout(app_header)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(12, 4, 12, 10)
        for icon_name in ("dashboard", "video", "user", "calendar", "group"):
            icon = QLabel()
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setPixmap(line_icon(icon_name, "#1877f2").pixmap(20, 20))
            toolbar.addWidget(icon, 1)
        screen_layout.addLayout(toolbar)
        self.feed_scroll = QScrollArea()
        self.feed_scroll.setObjectName("phoneFeedScroll")
        self.feed_scroll.setWidgetResizable(True)
        self.feed_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        screen_layout.addWidget(self.feed_scroll, 1)
        feed = QWidget()
        feed.setObjectName("facebookFeed")
        layout = QVBoxLayout(feed)
        layout.setContentsMargins(0, 8, 0, 8)
        post = QFrame()
        post.setObjectName("facebookPost")
        body = QVBoxLayout(post)
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(12)
        header = QHBoxLayout()
        self.avatar = QLabel("P")
        self.avatar.setObjectName("facebookAvatar")
        self.avatar.setFixedSize(40, 40)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.avatar)
        identity = QVBoxLayout()
        identity.setSpacing(2)
        self.page_name = QLabel("Page Facebook")
        self.page_name.setObjectName("facebookPage")
        self.page_name.setWordWrap(True)
        self.page_name.setTextFormat(Qt.TextFormat.PlainText)
        identity.addWidget(self.page_name)
        self.meta = QLabel("Bản xem trước · Công khai")
        self.meta.setObjectName("facebookMeta")
        self.meta.setWordWrap(True)
        identity.addWidget(self.meta)
        header.addLayout(identity, 1)
        header.addWidget(QLabel("···"))
        body.addLayout(header)
        self.content = QLabel()
        self.content.setWordWrap(True)
        self.content.setTextFormat(Qt.TextFormat.PlainText)
        self.content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.addWidget(self.content)
        self.media = MediaPreview()
        self.media.setFixedHeight(230)
        body.addWidget(self.media)
        self.video_caption = QLabel("▶ Video đính kèm")
        self.video_caption.setObjectName("facebookMeta")
        self.video_caption.setWordWrap(True)
        body.addWidget(self.video_caption)
        actions = QLabel("Thích     ·     Bình luận     ·     Chia sẻ")
        actions.setObjectName("facebookActions")
        actions.setWordWrap(True)
        actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(actions)
        layout.addWidget(post)
        layout.addStretch(1)
        self.feed_scroll.setWidget(feed)
        home = QLabel()
        home.setObjectName("phoneHome")
        home.setFixedSize(100, 4)
        screen_layout.addSpacing(8)
        screen_layout.addWidget(home, 0, Qt.AlignmentFlag.AlignHCenter)
        scene = QGraphicsScene(self)
        scene.addWidget(self.phone)
        scene.setSceneRect(self.phone.rect())
        self.phone_view = PhoneView(scene, self)
        self.phone_view.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.phone_view.setMinimumSize(0, 0)
        self.phone_view.setFrameShape(QFrame.Shape.NoFrame)
        self.phone_view.setStyleSheet("background: transparent; border: none;")
        self.phone_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.phone_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.phone_view.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        stage_layout.addWidget(self.phone_view)
        self.set_content("")
        self.set_media()

    def set_content(self, text: str) -> None:
        self.content.setText(text.strip() or "Nội dung bài đăng sẽ hiển thị ở đây sau khi tạo.")

    def set_page(self, name: str, scheduled: str = "") -> None:
        self.page_name.setText(name or "Page Facebook")
        self.avatar.setText((name or "P")[0].upper())
        self.meta.setText(("Dự kiến: " + scheduled if scheduled else "Bản xem trước") + " · Công khai")

    def set_media(self, pixmap: QPixmap | None = None, video: str = "", image_count: int = 1) -> None:
        self.media.clear()
        has_image = pixmap is not None and not pixmap.isNull()
        self.media.setVisible(has_image or bool(video))
        if has_image:
            self.media.setPixmap(pixmap)
        elif video:
            self.media.setText("▶\nVideo đã tạo")
        self.video_caption.setText("▶ " + video if video else f"{image_count} ảnh trong bài viết · Xem đủ ảnh ở tab Ảnh / video")
        self.video_caption.setVisible(bool(video) or (has_image and image_count > 1))

    def finish_video(self, name: str) -> None:
        self.set_media(QPixmap(self.media._original), name)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setFixedWidth(round((self.height() - 4) * self.phone.width() / self.phone.height()) + 4)
        self.layout().invalidate()
        self.layout().activate()
        self.height_changed.emit(self.height())
        self.phone_view.fitInView(self.phone_view.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
