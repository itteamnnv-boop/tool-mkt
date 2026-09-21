"""Tab: Bộ sưu tập — xem, mở lại, tái sử dụng hoặc xoá ảnh/video đã tạo trong lịch sử."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal, QUrl, QEvent, QTimer
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.storage import history_store
from app.ui.widgets.page_header import make_page_header
from app.ui.widgets.liquid_glass import GlassCard

CARD_WIDTH = 260
ITEMS_PER_TABLE = 60

FILTER_ALL = "all"
FILTER_IMAGES = "images"
FILTER_VIDEOS = "videos"


def _row_get(row: Any, key: str, default: str = "") -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return value if value is not None else default


def _row_id(row: Any) -> Any:
    try:
        return row["id"]
    except (KeyError, IndexError):
        return row["_id"]


def _format_created_at(value: Any) -> str:
    if isinstance(value, str):
        return value.replace("T", " ")
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except AttributeError:
        return str(value)


class _GalleryCard(GlassCard):
    use_for_post = Signal(Path, str)  # file_path, kind ("image" | "video")
    use_for_video_material = Signal(Path)
    use_for_tiktok = Signal(Path)
    use_for_youtube = Signal(Path)
    removed_from_history = Signal(object, str)  # item_id, table — card is gone, ask parent to refresh
    log_message = Signal(str, str)

    def __init__(self, kind: str, table: str, item_id: Any, created_at: str, caption: str, file_path: Path, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.table = table
        self.item_id = item_id
        self.file_path = file_path
        self.setObjectName("card")
        self.setMinimumWidth(CARD_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        meta = QHBoxLayout()
        badge = QLabel("ẢNH" if kind == "image" else "VIDEO")
        badge.setObjectName("mutedHint")
        meta.addWidget(badge)
        meta.addStretch()
        more = QPushButton("⋯")
        more.setObjectName("linkButton")
        more.setFixedWidth(40)
        more.setToolTip("Tuỳ chọn tệp")
        more.setAccessibleName("Tuỳ chọn tệp")
        more_menu = QMenu(more)
        more_menu.addAction("Xoá khỏi bộ sưu tập", self._on_remove_from_history)
        more_menu.addSeparator()
        delete_action = more_menu.addAction("Xoá vĩnh viễn tệp…", self._on_delete_file)
        delete_action.setEnabled(file_path.is_file())
        more.setMenu(more_menu)
        meta.addWidget(more)
        layout.addLayout(meta)

        self.thumb = QLabel()
        self.thumb.setObjectName("mediaPreview")
        self.thumb.setFixedHeight(190)
        self.thumb.setMinimumWidth(0)
        self.thumb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pixmap = QPixmap(str(file_path)) if kind == "image" and file_path.is_file() else QPixmap()
        self._load_thumbnail()
        layout.addWidget(self.thumb)

        caption_text = caption.strip() or file_path.name or "Chưa có mô tả"
        self.caption_label = QLabel()
        self.caption_label.setFixedHeight(42)
        self.caption_label.setWordWrap(False)
        self.caption_label.setToolTip(caption_text)
        self._caption = " ".join(caption_text.split())
        layout.addWidget(self.caption_label)
        date_label = QLabel(created_at[:16])
        date_label.setObjectName("mutedHint")
        layout.addWidget(date_label)
        self.setToolTip(str(file_path))
        exists = file_path.is_file()
        if not exists:
            date_label.setText("Không tìm thấy tệp trên máy")

        actions = QHBoxLayout()
        open_btn = QPushButton("Mở tệp")
        open_btn.setObjectName("linkButton")
        open_btn.setEnabled(exists)
        open_btn.clicked.connect(self._on_open)
        actions.addWidget(open_btn)
        use_btn = QPushButton("Sử dụng")
        use_btn.setObjectName("primaryButton")
        use_btn.setEnabled(exists)
        use_menu = QMenu(use_btn)
        use_menu.addAction("Đăng Facebook", lambda: self.use_for_post.emit(self.file_path, self.kind))
        if kind == "video":
            use_menu.addAction("Đăng TikTok", lambda: self.use_for_tiktok.emit(self.file_path))
            use_menu.addAction("Đăng YouTube", lambda: self.use_for_youtube.emit(self.file_path))
        else:
            use_menu.addAction("Làm vật liệu video", lambda: self.use_for_video_material.emit(self.file_path))
        use_btn.setMenu(use_menu)
        actions.addWidget(use_btn, 1)
        layout.addLayout(actions)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._load_thumbnail()
        # Two fully visible lines, with an ellipsis instead of a clipped paragraph.
        metrics = self.caption_label.fontMetrics()
        width = max(1, self.width() - 48)
        words = self._caption.split()
        first = ""
        while words and metrics.horizontalAdvance((first + " " + words[0]).strip()) <= width:
            first = (first + " " + words.pop(0)).strip()
        if not first and words:
            first = metrics.elidedText(words.pop(0), Qt.TextElideMode.ElideRight, width)
        second = metrics.elidedText(" ".join(words), Qt.TextElideMode.ElideRight, width)
        self.caption_label.setText(first + ("\n" + second if second else ""))

    def _load_thumbnail(self) -> None:
        if not self._pixmap.isNull():
            self.thumb.setPixmap(self._pixmap.scaled(
                max(1, self.thumb.width() - 12), 178,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            self.thumb.setText("▶\nVideo" if self.kind == "video" else "Không có ảnh xem trước")

    def _on_open(self) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.file_path.resolve()))):
            self.log_message.emit("Không thể mở file. Hãy kiểm tra ứng dụng xem ảnh/video mặc định.", "error")

    def _on_remove_from_history(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Xoá khỏi bộ sưu tập",
            f"Xoá mục này khỏi lịch sử/bộ sưu tập?\n{self.file_path.name}\n\n"
            "File trên máy vẫn được giữ nguyên — chỉ gỡ bản ghi khỏi danh sách.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            history_store.delete_item(self.table, self.item_id)
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit(f"Không xoá được bản ghi: {exc}", "error")
            return
        self.log_message.emit(f"Đã xoá khỏi bộ sưu tập: {self.file_path.name}", "info")
        self.removed_from_history.emit(self.item_id, self.table)

    def _on_delete_file(self) -> None:
        confirm = QMessageBox.warning(
            self,
            "Xoá vĩnh viễn",
            f"Xoá VĨNH VIỄN file này khỏi máy tính? Không thể khôi phục.\n\n{self.file_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self.file_path.unlink(missing_ok=True)
        except OSError as exc:
            self.log_message.emit(f"Không xoá được file: {exc}", "error")
            return
        try:
            history_store.delete_item(self.table, self.item_id)
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit(f"Đã xoá file nhưng không xoá được bản ghi lịch sử: {exc}", "error")
        else:
            self.log_message.emit(f"Đã xoá vĩnh viễn: {self.file_path.name}", "info")
        self.removed_from_history.emit(self.item_id, self.table)


class GalleryTab(QWidget):
    use_for_post_image = Signal(Path)
    use_for_post_video = Signal(Path)
    use_for_video_material = Signal(Path)
    use_for_tiktok_video = Signal(Path)
    use_for_youtube_video = Signal(Path)
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        self._items = []
        self._cards = []
        self._columns = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(make_page_header(
            "Bộ sưu tập", "Không gian lưu giữ ý tưởng. Chọn ảnh hoặc video để tiếp tục sáng tạo."
        ))
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm theo mô tả hoặc tên tệp…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(120)
        self.search_input.setAccessibleName("Tìm trong bộ sưu tập")
        toolbar.addWidget(self.search_input, 1)
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Tất cả", FILTER_ALL)
        self.filter_combo.addItem("Ảnh", FILTER_IMAGES)
        self.filter_combo.addItem("Video", FILTER_VIDEOS)
        toolbar.addWidget(self.filter_combo)
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Mới nhất", True)
        self.sort_combo.addItem("Cũ nhất", False)
        toolbar.addWidget(self.sort_combo)
        self.refresh_btn = QPushButton("Làm mới")
        self.refresh_btn.setObjectName("linkButton")
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("mutedHint")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(300)
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.grid = QGridLayout(container)
        self.grid.setContentsMargins(0, 0, 8, 0)
        self.grid.setSpacing(16)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(container)
        layout.addWidget(self.scroll, 1)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._arrange_cards)
        self.scroll.viewport().installEventFilter(self)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._render_items)
        self.search_input.textChanged.connect(lambda: self._search_timer.start())
        self.filter_combo.currentIndexChanged.connect(self._render_items)
        self.sort_combo.currentIndexChanged.connect(self._render_items)

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._resize_timer.start(0)
        return super().eventFilter(watched, event)

    def refresh(self) -> None:
        try:
            images = history_store.list_recent("images", ITEMS_PER_TABLE)
            videos = history_store.list_recent("videos", ITEMS_PER_TABLE)
        except Exception as exc:
            self.summary_label.setText("Không tải được bộ sưu tập. Hãy thử làm mới.")
            self.log_message.emit(f"Không tải được bộ sưu tập: {exc}", "error")
            return
        self._items = [("image", "images", item) for item in images]
        self._items += [("video", "videos", item) for item in videos]
        self._render_items()

    def _render_items(self) -> None:
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        self._cards = []
        selected = self.filter_combo.currentData()
        query = self.search_input.text().strip().casefold()
        items = []
        for kind, table, item in self._items:
            caption = str(_row_get(item, "prompt" if kind == "image" else "script"))
            path = Path(str(_row_get(item, "file_path")))
            if selected != FILTER_ALL and table != selected:
                continue
            if query and query not in (caption + " " + path.name).casefold():
                continue
            items.append((kind, table, item, caption, path))
        items.sort(key=lambda entry: _format_created_at(_row_get(entry[2], "created_at")),
                   reverse=bool(self.sort_combo.currentData()))
        image_count = sum(kind == "image" for kind, _, _ in self._items)
        video_count = len(self._items) - image_count
        self.summary_label.setText(
            f"{len(items)} mục hiển thị  ·  {image_count} ảnh / {video_count} video"
            f"  ·  {ITEMS_PER_TABLE} mục gần nhất mỗi loại"
        )
        for kind, table, item, caption, path in items:
            card = _GalleryCard(kind, table, _row_id(item),
                                _format_created_at(_row_get(item, "created_at")), caption, path)
            card.use_for_post.connect(self._on_use_for_post)
            card.use_for_video_material.connect(self.use_for_video_material)
            card.use_for_tiktok.connect(self.use_for_tiktok_video)
            card.use_for_youtube.connect(self.use_for_youtube_video)
            card.removed_from_history.connect(lambda *_args: self.refresh())
            card.log_message.connect(self.log_message)
            self._cards.append(card)
        if not items:
            empty = QLabel(
                "Chưa có ảnh hoặc video\nTạo nội dung đầu tiên để bắt đầu bộ sưu tập của bạn."
                if not self._items else
                "Không tìm thấy nội dung phù hợp\nThử từ khoá khác hoặc chọn Tất cả."
            )
            empty.setObjectName("mutedHint")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(240)
            self.grid.addWidget(empty, 0, 0)
        self._arrange_cards()

    def _arrange_cards(self) -> None:
        columns = max(1, (self.scroll.viewport().width() - 8 + 16) // (CARD_WIDTH + 16))
        for column in range(max(self._columns, columns)):
            self.grid.setColumnStretch(column, 0)
            self.grid.setColumnMinimumWidth(column, 0)
        self._columns = columns
        for card in self._cards:
            self.grid.removeWidget(card)
        for index, card in enumerate(self._cards):
            self.grid.addWidget(card, index // columns, index % columns)
        if self._cards:
            for column in range(columns):
                self.grid.setColumnStretch(column, 1)

    def _on_use_for_post(self, path: Path, kind: str) -> None:
        if kind == "image":
            self.use_for_post_image.emit(path)
        else:
            self.use_for_post_video.emit(path)
