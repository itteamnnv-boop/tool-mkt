"""Tab: Bộ sưu tập — xem, mở lại, tái sử dụng hoặc xoá ảnh/video đã tạo trong lịch sử."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
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

COLUMNS = 4
CARD_WIDTH = 210
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
        self.setFixedWidth(CARD_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.thumb = QLabel()
        self.thumb.setObjectName("mediaPreview")
        self.thumb.setFixedSize(CARD_WIDTH - 20, 130)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_thumbnail()
        layout.addWidget(self.thumb)

        date_label = QLabel(created_at)
        date_label.setObjectName("mutedHint")
        layout.addWidget(date_label)

        caption_text = caption.strip() or "(không có mô tả)"
        caption_label = QLabel(caption_text[:140] + ("…" if len(caption_text) > 140 else ""))
        caption_label.setWordWrap(True)
        caption_label.setMaximumHeight(60)
        caption_label.setToolTip(caption_text)
        layout.addWidget(caption_label)

        exists = file_path.exists()
        if not exists:
            missing = QLabel("⚠ Không tìm thấy file (có thể đã bị xoá hoặc di chuyển).")
            missing.setObjectName("mutedHint")
            missing.setWordWrap(True)
            layout.addWidget(missing)

        open_btn = QPushButton("Mở")
        open_btn.setEnabled(exists)
        open_btn.clicked.connect(self._on_open)
        layout.addWidget(open_btn)

        post_btn = QPushButton("→ Dùng để đăng Facebook")
        post_btn.setObjectName("linkButton")
        post_btn.setEnabled(exists)
        post_btn.clicked.connect(lambda: self.use_for_post.emit(self.file_path, self.kind))
        layout.addWidget(post_btn)

        if kind == "video":
            tiktok_btn = QPushButton("→ Dùng để đăng TikTok")
            tiktok_btn.setObjectName("linkButton")
            tiktok_btn.setEnabled(exists)
            tiktok_btn.clicked.connect(lambda: self.use_for_tiktok.emit(self.file_path))
            layout.addWidget(tiktok_btn)

            youtube_btn = QPushButton("→ Dùng để đăng YouTube")
            youtube_btn.setObjectName("linkButton")
            youtube_btn.setEnabled(exists)
            youtube_btn.clicked.connect(lambda: self.use_for_youtube.emit(self.file_path))
            layout.addWidget(youtube_btn)

        if kind == "image":
            material_btn = QPushButton("→ Dùng làm vật liệu Video")
            material_btn.setObjectName("linkButton")
            material_btn.setEnabled(exists)
            material_btn.clicked.connect(lambda: self.use_for_video_material.emit(self.file_path))
            layout.addWidget(material_btn)

        remove_btn = QPushButton("🗑 Xoá khỏi bộ sưu tập")
        remove_btn.setObjectName("linkButton")
        remove_btn.clicked.connect(self._on_remove_from_history)
        layout.addWidget(remove_btn)

        delete_file_btn = QPushButton("Xoá vĩnh viễn cả file trên máy")
        delete_file_btn.setEnabled(exists)
        delete_file_btn.clicked.connect(self._on_delete_file)
        layout.addWidget(delete_file_btn)

    def _load_thumbnail(self) -> None:
        if self.kind == "image" and self.file_path.exists():
            pixmap = QPixmap(str(self.file_path))
            if not pixmap.isNull():
                self.thumb.setPixmap(
                    pixmap.scaled(
                        self.thumb.width() - 8,
                        self.thumb.height() - 8,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        self.thumb.setText("🎬 Video" if self.kind == "video" else "🖼️ Ảnh (không xem trước được)")

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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.addWidget(
            make_page_header("📚 Bộ sưu tập", "Xem lại, tái sử dụng hoặc xoá ảnh/video đã tạo."), 1
        )
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Tất cả", FILTER_ALL)
        self.filter_combo.addItem("Ảnh", FILTER_IMAGES)
        self.filter_combo.addItem("Video", FILTER_VIDEOS)
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        header_row.addWidget(self.filter_combo)
        self.refresh_btn = QPushButton("↻ Làm mới")
        self.refresh_btn.setObjectName("linkButton")
        self.refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(self.refresh_btn)
        layout.addLayout(header_row)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("mutedHint")
        layout.addWidget(self.summary_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        container = QWidget()
        self.grid = QGridLayout(container)
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(container)
        layout.addWidget(self.scroll, 1)

    def refresh(self) -> None:
        self._clear_grid()
        selected = self.filter_combo.currentData() or FILTER_ALL

        images = history_store.list_recent("images", ITEMS_PER_TABLE) if selected != FILTER_VIDEOS else []
        videos = history_store.list_recent("videos", ITEMS_PER_TABLE) if selected != FILTER_IMAGES else []
        self.summary_label.setText(f"{len(images)} ảnh  •  {len(videos)} video (tối đa {ITEMS_PER_TABLE} mục gần nhất mỗi loại)")

        row = 0
        if selected != FILTER_VIDEOS:
            row = self._add_section("🖼️ Ảnh đã tạo", "images", "image", images, row)
        if selected != FILTER_IMAGES:
            row = self._add_section("🎬 Video đã tạo", "videos", "video", videos, row)
        if row == 0:
            empty = QLabel("Chưa có ảnh hoặc video nào được tạo.")
            empty.setObjectName("mutedHint")
            self.grid.addWidget(empty, 0, 0, 1, COLUMNS)

    def _add_section(self, title: str, table: str, kind: str, items: list, start_row: int) -> int:
        header = QLabel(title)
        header.setObjectName("cardTitle")
        self.grid.addWidget(header, start_row, 0, 1, COLUMNS)
        row = start_row + 1

        if not items:
            empty = QLabel("Chưa có mục nào.")
            empty.setObjectName("mutedHint")
            self.grid.addWidget(empty, row, 0, 1, COLUMNS)
            return row + 1

        col = 0
        caption_key = "prompt" if kind == "image" else "script"
        for item in items:
            card = _GalleryCard(
                kind=kind,
                table=table,
                item_id=_row_id(item),
                created_at=_format_created_at(_row_get(item, "created_at")),
                caption=str(_row_get(item, caption_key)),
                file_path=Path(str(_row_get(item, "file_path"))),
            )
            card.use_for_post.connect(self._on_use_for_post)
            card.use_for_video_material.connect(self.use_for_video_material)
            card.use_for_tiktok.connect(self.use_for_tiktok_video)
            card.use_for_youtube.connect(self.use_for_youtube_video)
            card.removed_from_history.connect(lambda *_args: self.refresh())
            card.log_message.connect(self.log_message)
            self.grid.addWidget(card, row, col)
            col += 1
            if col >= COLUMNS:
                col = 0
                row += 1
        if col != 0:
            row += 1
        return row + 1

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_use_for_post(self, path: Path, kind: str) -> None:
        if kind == "image":
            self.use_for_post_image.emit(path)
        else:
            self.use_for_post_video.emit(path)
