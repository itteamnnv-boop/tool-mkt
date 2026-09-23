"""Visual material editor: image-space selections, masked edits and version history."""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import shutil

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QApplication, QLabel, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from app import config
from app.core.image_client import ImageClient
from app.core.image_layers import ImageLayer, ImageLayerClient, DEFAULT_LAYER_MODEL, LAYER_MODELS
from app.storage import history_store
from app.workers.async_worker import Worker


class SelectionCanvas(QGraphicsView):
    region_added = Signal(QRectF)
    zoom_changed = Signal(int)
    layer_clicked = Signal(QPointF)
    brush_stroke = Signal(QPointF, QPointF, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QColor("#17191d"))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.image = QImage()
        self._start = None
        self._draft = None
        self._overlays = []
        self.selecting = True
        self.mode_index = 0
        self._brush_point = None

    def load(self, image: QImage):
        self.scene().clear()
        self._overlays = []
        self._start = self._draft = None
        self.image = image
        self.scene().addPixmap(QPixmap.fromImage(image))
        self.setSceneRect(QRectF(0, 0, image.width(), image.height()))
        self.fit_image()

    def fit_image(self):
        if not self.image.isNull():
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.zoom_changed.emit(round(self.transform().m11() * 100))

    def zoom(self, factor):
        scale = self.transform().m11() * factor
        if 0.02 <= scale <= 16:
            self.scale(factor, factor)
            self.zoom_changed.emit(round(self.transform().m11() * 100))

    def set_mode(self, index):
        self.mode_index = index
        self.selecting = index == 0
        self.setDragMode(self.DragMode.ScrollHandDrag if index == 1 else self.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.OpenHandCursor if index == 1 else Qt.CursorShape.CrossCursor)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
            event.accept()
        else:
            super().wheelEvent(event)

    def _point(self, event):
        point = self.mapToScene(event.position().toPoint())
        return QPointF(max(0, min(point.x(), self.image.width())),
                       max(0, min(point.y(), self.image.height())))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.mode_index >= 2:
            if not self.sceneRect().contains(self.mapToScene(event.position().toPoint())):
                return
            point = self._point(event)
            if self.mode_index == 2:
                self.layer_clicked.emit(point)
            else:
                self._brush_point = point
                self.brush_stroke.emit(point, point, self.mode_index == 4)
            return
        if self.selecting and event.button() == Qt.MouseButton.LeftButton and not self.image.isNull():
            if not self.sceneRect().contains(self.mapToScene(event.position().toPoint())):
                return
            self._start = self._point(event)
            pen = QPen(QColor("#65b7ff"), 2)
            pen.setCosmetic(True)
            self._draft = self.scene().addRect(QRectF(), pen, QColor(60, 150, 255, 45))
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._brush_point is not None:
            point = self._point(event)
            self.brush_stroke.emit(self._brush_point, point, self.mode_index == 4)
            self._brush_point = point
            return
        if self._start is not None:
            self._draft.setRect(QRectF(self._start, self._point(event)).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._brush_point is not None:
            self._brush_point = None
            return
        if self._start is not None and event.button() == Qt.MouseButton.LeftButton:
            rect = QRectF(self._start, self._point(event)).normalized().intersected(self.sceneRect())
            self.scene().removeItem(self._draft)
            self._draft = self._start = None
            if rect.width() >= 2 and rect.height() >= 2:
                self.region_added.emit(rect)
            return
        super().mouseReleaseEvent(event)

    def show_regions(self, regions):
        for overlay in self._overlays:
            self.scene().removeItem(overlay)
        self._overlays = []
        pen = QPen(QColor("#65b7ff"), 2)
        pen.setCosmetic(True)
        for rect in regions:
            if isinstance(rect, ImageLayer):
                overlay = rect.mask.copy()
                painter = QPainter(overlay)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                painter.fillRect(overlay.rect(), QColor(60, 150, 255, 100))
                painter.end()
                self._overlays.append(self.scene().addPixmap(QPixmap.fromImage(overlay)))
            else:
                self._overlays.append(self.scene().addRect(rect, pen, QColor(60, 150, 255, 45)))

    def mask(self, regions) -> QImage:
        mask = QImage(self.image.size(), QImage.Format.Format_ARGB32)
        mask.fill(Qt.GlobalColor.white)
        painter = QPainter(mask)
        for rect in regions:
            if isinstance(rect, ImageLayer):
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
                painter.drawImage(0, 0, rect.mask)
            else:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                painter.fillRect(rect.toAlignedRect().intersected(mask.rect()), Qt.GlobalColor.transparent)
        painter.end()
        return mask


class ImageEditorDialog(QDialog):
    def __init__(self, path: Path, versions=None, face_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chỉnh sửa hình ảnh")
        self.resize(1280, 820)
        self.setMinimumSize(880, 600)
        self.versions = list(versions or [(path, "Ảnh ban đầu")])
        self.current_path = path
        self.face_path = face_path
        self._busy = False
        self._worker = None
        self._temp = None
        self._layer_cache = {}
        self._edit_snapshot = None
        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["Chọn vùng", "Di chuyển ảnh", "Chọn lớp AI", "Tô thêm vào lớp", "Xóa bớt khỏi lớp"])
        toolbar.addWidget(self.mode)
        self.zoom_label = QLabel()
        self.canvas = SelectionCanvas()
        self.mode.currentIndexChanged.connect(self.canvas.set_mode)
        self.canvas.zoom_changed.connect(lambda value: self.zoom_label.setText(f"{value}%"))
        for title, action in (("−", lambda: self.canvas.zoom(1 / 1.2)), ("+", lambda: self.canvas.zoom(1.2)),
                              ("Vừa màn hình", self.canvas.fit_image), ("100%", self._actual_size)):
            button = QPushButton(title)
            button.clicked.connect(action)
            toolbar.addWidget(button)
        toolbar.addWidget(self.zoom_label)
        toolbar.addWidget(QLabel("Cọ (px):"))
        self.brush_size = QSpinBox()
        self.brush_size.setRange(2, 200)
        self.brush_size.setValue(20)
        toolbar.addWidget(self.brush_size)
        toolbar.addStretch()
        root.addLayout(toolbar)
        body = QHBoxLayout()
        self.history = QListWidget()
        self.history.setFixedWidth(160)
        self.history.setIconSize(QSize(100, 90))
        self.history.setViewMode(QListWidget.ViewMode.IconMode)
        self.history.setFlow(QListWidget.Flow.TopToBottom)
        self.history.setWrapping(False)
        self.history.setMovement(QListWidget.Movement.Static)
        self.history.setGridSize(QSize(138, 140))
        self.history.setWordWrap(True)
        self.history.currentRowChanged.connect(self._select_version)
        body.addWidget(self.history)
        body.addWidget(self.canvas, 1)
        self.sidebar = QWidget()
        side = QVBoxLayout(self.sidebar)
        side.addWidget(QLabel("Vùng chỉnh sửa"))
        side.addWidget(QLabel("Model phân tích lớp"))
        self.layer_model = QComboBox()
        for label, model in LAYER_MODELS:
            self.layer_model.addItem(label, model)
        configured_model = config.load_settings().get("openai_layer_model", DEFAULT_LAYER_MODEL)
        if self.layer_model.findData(configured_model) < 0:
            self.layer_model.addItem(configured_model, configured_model)
        self.layer_model.setCurrentIndex(self.layer_model.findData(configured_model))
        self.layer_model.setToolTip("Grok dùng Grok API key; GPT dùng OpenAI API key trong Cài đặt. Biên của mọi model vẫn cần kiểm tra.")
        side.addWidget(self.layer_model)
        self.analyze_btn = QPushButton("AI phân tích lớp")
        self.analyze_btn.clicked.connect(self._analyze_layers)
        side.addWidget(self.analyze_btn)
        hint = QLabel("Phân tích rồi bấm lên ảnh để chọn lớp. Ctrl + bấm để chọn nhiều lớp; dùng cọ để sửa biên.")
        hint.setWordWrap(True)
        side.addWidget(hint)
        self.regions = QListWidget()
        self.regions.setMaximumHeight(200)
        self.regions.itemChanged.connect(self._refresh_regions)
        self.regions.itemClicked.connect(self._select_layer_item)
        self.regions.currentItemChanged.connect(self._describe_region)
        self.regions.setIconSize(QSize(38, 38))
        side.addWidget(self.regions)
        self.canvas.region_added.connect(self.add_region)
        self.canvas.layer_clicked.connect(self._pick_layer)
        self.canvas.brush_stroke.connect(self._paint_layer)
        self.layer_description = QLabel()
        self.layer_description.setWordWrap(True)
        side.addWidget(self.layer_description)
        self.export_layer_btn = QPushButton("Lưu lớp thành vật liệu PNG")
        self.export_layer_btn.clicked.connect(self._export_layer)
        side.addWidget(self.export_layer_btn)
        remove = QPushButton("Xóa vùng đang chọn")
        remove.clicked.connect(self._remove_region)
        side.addWidget(remove)
        clear = QPushButton("Bỏ tất cả vùng / sửa toàn ảnh")
        clear.clicked.connect(self._clear_regions)
        side.addWidget(clear)
        crop = QPushButton("Cắt ảnh theo vùng đang chọn")
        crop.clicked.connect(self._crop)
        side.addWidget(crop)
        self.instruction = QTextEdit()
        self.instruction.setMinimumHeight(85)
        self.instruction.setPlaceholderText("Mô tả chỉnh sửa: đổi màu áo, thêm đạo cụ, thay nền…")
        side.addWidget(self.instruction, 1)
        self.apply_btn = QPushButton("Áp dụng chỉnh sửa AI")
        self.apply_btn.setObjectName("primaryButton")
        self.apply_btn.clicked.connect(self._apply)
        side.addWidget(self.apply_btn)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFixedWidth(320)
        side_scroll.setWidget(self.sidebar)
        body.addWidget(side_scroll)
        root.addLayout(body, 1)
        self.status = QLabel("Khoanh vùng rồi nhập yêu cầu; không chọn vùng sẽ chỉnh toàn ảnh.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        footer = QHBoxLayout()
        self.export_btn = QPushButton("Lưu ảnh thành…")
        self.export_btn.clicked.connect(self._export)
        footer.addWidget(self.export_btn)
        footer.addStretch()
        self.use_btn = QPushButton("Dùng ảnh này làm vật liệu")
        self.use_btn.setObjectName("primaryButton")
        self.use_btn.clicked.connect(self.accept)
        footer.addWidget(self.use_btn)
        root.addLayout(footer)
        self._populate_history(path)
        QTimer.singleShot(0, self.canvas.fit_image)

    def _actual_size(self):
        self.canvas.resetTransform()
        self.zoom_label.setText("100%")

    def _populate_history(self, selected):
        self.history.blockSignals(True)
        self.history.clear()
        index = 0
        for i, (path, description) in enumerate(self.versions):
            item = QListWidgetItem(QIcon(str(path)), f"{i + 1}. {description[:35]}")
            item.setToolTip(description)
            self.history.addItem(item)
            if path == selected:
                index = i
        self.history.setCurrentRow(index)
        self.history.blockSignals(False)
        self._select_version(index)

    def _select_version(self, index):
        if self._busy or index < 0:
            return
        path = self.versions[index][0]
        image = QImage(str(path))
        if image.isNull():
            self.status.setText("Không đọc được phiên bản ảnh đã chọn.")
            self.history.blockSignals(True)
            self.history.setCurrentRow(next(i for i, version in enumerate(self.versions) if version[0] == self.current_path))
            self.history.blockSignals(False)
            return
        self.current_path = path
        self.canvas.load(image)
        self._clear_regions(discard=False)
        for layer in self._layer_cache.get(path, []):
            self._add_layer_item(layer)

    def add_region(self, rect):
        item = QListWidgetItem(f"Vùng {self.regions.count() + 1}")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(Qt.ItemDataRole.UserRole, rect)
        item.setCheckState(Qt.CheckState.Checked)
        self.regions.addItem(item)
        self.regions.setCurrentItem(item)
        self._refresh_regions()

    def checked_regions(self):
        return [self.regions.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.regions.count())
                if self.regions.item(i).checkState() == Qt.CheckState.Checked]

    def _refresh_regions(self):
        for i in range(self.regions.count()):
            item = self.regions.item(i)
            layer = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(layer, ImageLayer):
                layer.name = item.text()
        self.canvas.show_regions(self.checked_regions())

    def _describe_region(self, current=None, previous=None):
        item = self.regions.currentItem()
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.layer_description.setText(
            (f"{value.description}\n{value.position_text()}" +
             ("\nBiên ước lượng — cần kiểm tra bằng cọ." if not value.refined else ""))
            if isinstance(value, ImageLayer) else ""
        )

    def _select_layer_item(self, item):
        if not QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
            self.regions.blockSignals(True)
            for i in range(self.regions.count()):
                self.regions.item(i).setCheckState(Qt.CheckState.Checked if self.regions.item(i) is item else Qt.CheckState.Unchecked)
            self.regions.blockSignals(False)
        self.regions.setCurrentItem(item)
        self._refresh_regions()
        self._describe_region()

    def _pick_layer(self, point):
        candidates = []
        for i in range(self.regions.count()):
            item = self.regions.item(i)
            layer = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(layer, ImageLayer) and layer.contains(point):
                candidates.append((layer.area, i))
        if candidates:
            item = self.regions.item(min(candidates)[1])
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
                item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)
            self._select_layer_item(item)
        else:
            if not QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
                self.regions.blockSignals(True)
                for i in range(self.regions.count()):
                    self.regions.item(i).setCheckState(Qt.CheckState.Unchecked)
                self.regions.blockSignals(False)
                self.regions.setCurrentRow(-1)
                self._refresh_regions()
            self.status.setText("Chưa có lớp tại vị trí này. Chọn lớp trong danh sách và tô thêm, hoặc khoanh vùng thủ công.")

    def _paint_layer(self, start, end, erase):
        item = self.regions.currentItem()
        layer = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(layer, ImageLayer):
            self.status.setText("Chọn một lớp AI trước khi tô hoặc xóa biên.")
            return
        painter = QPainter(layer.mask)
        if erase:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        pen = QPen(Qt.GlobalColor.white, self.brush_size.value(), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.end()
        layer.update_geometry()
        item.setIcon(QIcon(QPixmap.fromImage(layer.cutout(self.canvas.image))))
        item.setToolTip(layer.description + "\n" + layer.position_text())
        item.setCheckState(Qt.CheckState.Checked)
        self._refresh_regions()
        self._describe_region()

    def _add_layer_item(self, layer):
        item = QListWidgetItem(QIcon(QPixmap.fromImage(layer.cutout(self.canvas.image))), layer.name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(Qt.ItemDataRole.UserRole, layer)
        item.setToolTip(layer.description + "\n" + layer.position_text())
        item.setCheckState(Qt.CheckState.Unchecked)
        self.regions.addItem(item)

    def _analyze_layers(self):
        if self._busy:
            return
        try:
            model = self.layer_model.currentData()
            secret = "grok_api_key" if model.startswith("grok-") else "openai_api_key"
            client = ImageLayerClient(config.get_secret(secret), model)
            settings = config.load_settings()
            settings["openai_layer_model"] = model
            config.save_settings(settings)
        except (ValueError, OSError) as exc:
            self._error(str(exc))
            return
        self._set_busy(True)
        self.status.setText(f"{model} đang phân tích lớp ảnh…")
        self._worker = Worker(client.analyze, self.current_path)
        self._worker.progress.connect(self.status.setText)
        self._worker.finished.connect(self._layers_done)
        self._worker.error.connect(self._error)
        self._worker.start()

    def _layers_done(self, layers):
        self._set_busy(False)
        self._layer_cache[self.current_path] = layers
        # Replace AI layers only; retain manually drawn regions.
        for i in range(self.regions.count() - 1, -1, -1):
            if isinstance(self.regions.item(i).data(Qt.ItemDataRole.UserRole), ImageLayer):
                self.regions.takeItem(i)
            else:
                self.regions.item(i).setCheckState(Qt.CheckState.Unchecked)
        for layer in layers:
            self._add_layer_item(layer)
        self.mode.setCurrentIndex(2)
        self._refresh_regions()
        approximate = sum(not layer.refined for layer in layers)
        detail = f" {approximate} lớp chưa tinh chỉnh được biên hoặc có vùng chồng lấn." if approximate else ""
        self.status.setText(f"Đã phân tích {len(layers)} lớp.{detail} Bấm lên ảnh để chọn; kiểm tra và sửa biên bằng cọ trước khi áp dụng.")

    def _export_layer(self):
        item = self.regions.currentItem()
        layer = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(layer, ImageLayer):
            self.status.setText("Chọn một lớp AI để lưu vật liệu riêng.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Lưu lớp vật liệu", "material.png", "PNG (*.png)")
        if filename:
            if layer.cutout(self.canvas.image).save(filename, "PNG"):
                history_store.add_image(f"Tách lớp: {item.text()}", filename)
                self.status.setText(f"Đã lưu vật liệu nền trong suốt: {filename}")
            else:
                self.status.setText("Không lưu được lớp vật liệu.")

    def _remove_region(self):
        row = self.regions.currentRow()
        if row >= 0:
            layer = self.regions.takeItem(row).data(Qt.ItemDataRole.UserRole)
            if isinstance(layer, ImageLayer):
                self._layer_cache[self.current_path] = [v for v in self._layer_cache.get(self.current_path, []) if v is not layer]
        self._refresh_regions()

    def _clear_regions(self, checked=False, *, discard=True):
        if discard:
            self._layer_cache.pop(self.current_path, None)
        self.regions.clear()
        self._refresh_regions()

    def _set_busy(self, busy):
        self._busy = busy
        for widget in (self.canvas, self.history, self.sidebar, self.mode, self.use_btn, self.export_btn):
            widget.setEnabled(not busy)

    def _cleanup(self):
        if self._temp:
            self._temp.cleanup()
            self._temp = None

    def _apply(self):
        if self._busy:
            return
        instruction = self.instruction.toPlainText().strip()
        if not instruction:
            self.status.setText("Nhập yêu cầu chỉnh sửa trước khi áp dụng.")
            return
        try:
            ImageClient.validate_reference_image(self.current_path)
            if self.face_path:
                ImageClient.validate_reference_image(self.face_path)
            client = ImageClient(config.get_secret("openai_api_key"), config.load_settings()["openai_image_model"])
            regions = self.checked_regions()
            if not regions and self.regions.count() and self.mode.currentIndex() >= 2:
                raise ValueError("Chưa chọn lớp để chỉnh sửa. Bấm vào một lớp hoặc bỏ tất cả vùng để sửa toàn ảnh.")
            if any(isinstance(region, ImageLayer) and not region.area for region in regions):
                raise ValueError("Lớp đang chọn không còn điểm ảnh. Tô thêm vùng hoặc bỏ chọn lớp trống.")
            mask_path = None
            source = self.current_path
            if regions:
                self._temp = TemporaryDirectory(prefix="material-edit-")
                source = Path(self._temp.name) / "source.png"
                mask_path = Path(self._temp.name) / "mask.png"
                if not self.canvas.image.save(str(source), "PNG") or not self.canvas.mask(regions).save(str(mask_path), "PNG"):
                    raise ValueError("Không lưu được vùng chỉnh sửa.")
                self._edit_snapshot = (self.canvas.image.copy(), self.canvas.mask(regions))
            target = 1 if regions or not self.face_path else 2
            prompt = f"Chỉnh sửa ảnh {target}. Giữ nguyên các chi tiết không được yêu cầu thay đổi. Yêu cầu: {instruction}"
            if regions:
                prompt += " Chỉ chỉnh các vùng được đánh dấu trong mask, giữ nguyên phần ngoài vùng chọn."
                for i in range(self.regions.count()):
                    item = self.regions.item(i)
                    layer = item.data(Qt.ItemDataRole.UserRole)
                    if item.checkState() == Qt.CheckState.Checked:
                        if isinstance(layer, ImageLayer):
                            prompt += f"\nLớp cần chỉnh: {item.text()}; {layer.description}; {layer.position_text()}."
                        else:
                            prompt += f"\nVùng cần chỉnh: {item.text()}; x={layer.x():.0f}, y={layer.y():.0f}, rộng={layer.width():.0f}, cao={layer.height():.0f} px."
                prompt += f"\nKích thước ảnh gốc: {self.canvas.image.width()}×{self.canvas.image.height()} px."
            if self.face_path:
                prompt += f" Ảnh {2 if regions else 1} là khuôn mặt tham chiếu, giữ các đặc điểm nhận diện."
            size = "1024x1024" if self.canvas.image.width() == self.canvas.image.height() else (
                "1536x1024" if self.canvas.image.width() > self.canvas.image.height() else "1024x1536")
            self._worker = Worker(client.generate_image, prompt=prompt, size=size, dest_dir=config.output_dir("images"),
                                  reference_image_path=source, face_image_path=self.face_path, mask_path=mask_path)
            self._worker.finished.connect(lambda path: self._done(path, instruction, prompt))
            self._worker.error.connect(self._error)
            self._set_busy(True)
            self.status.setText("Đang chỉnh sửa vùng đã chọn…" if regions else "Đang chỉnh sửa toàn ảnh…")
            self._worker.start()
        except (ValueError, OSError) as exc:
            self._error(str(exc))

    def _done(self, path, description, prompt):
        self._cleanup()
        self._set_busy(False)
        if QImage(str(path)).isNull():
            self._error("Không đọc được ảnh kết quả. Ảnh trước vẫn được giữ.")
            return
        if self._edit_snapshot is not None:
            original, mask = self._edit_snapshot
            edited = QImage(str(path)).scaled(original.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_ARGB32)
            painter = QPainter(edited)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            painter.drawImage(0, 0, mask)
            painter.end()
            composite = original.convertToFormat(QImage.Format.Format_ARGB32)
            painter = QPainter(composite)
            painter.drawImage(0, 0, edited)
            painter.end()
            composed_path = Path(path).with_name(f"region_edit_{uuid4().hex}.png")
            if not composite.save(str(composed_path), "PNG"):
                self._error("Không lưu được ảnh chỉnh sửa theo vùng.")
                return
            path = composed_path
            self._edit_snapshot = None
        self.versions.append((path, description))
        history_store.add_image(prompt, str(path))
        self._populate_history(path)
        self.instruction.clear()
        self.status.setText("Đã tạo phiên bản mới. Có thể sửa tiếp hoặc dùng ảnh này làm vật liệu.")

    def _error(self, message):
        self._edit_snapshot = None
        self._cleanup()
        self._set_busy(False)
        self.status.setText(f"Lỗi: {message}")

    def _crop(self):
        item = self.regions.currentItem()
        if item is None:
            self.status.setText("Chọn một vùng để cắt ảnh.")
            return
        geometry = item.data(Qt.ItemDataRole.UserRole)
        rect = (geometry.rect if isinstance(geometry, ImageLayer) else geometry).toAlignedRect().intersected(self.canvas.image.rect())
        try:
            path = config.output_dir("images") / f"crop_{uuid4().hex}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            if rect.isEmpty() or not self.canvas.image.copy(rect).save(str(path), "PNG"):
                raise ValueError("Không lưu được ảnh đã cắt.")
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            return
        self._done(path, "Cắt ảnh", "Cắt ảnh theo vùng được chọn")

    def _export(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Lưu ảnh", self.current_path.name, "Ảnh (*.png *.jpg *.jpeg *.webp)")
        if filename:
            try:
                path = Path(filename)
                if path.resolve() != self.current_path.resolve():
                    if path.suffix.lower() == self.current_path.suffix.lower():
                        shutil.copyfile(self.current_path, path)
                    elif not self.canvas.image.save(str(path)):
                        raise ValueError("Không hỗ trợ định dạng ảnh đã chọn.")
                self.status.setText(f"Đã lưu ảnh: {filename}")
            except (OSError, ValueError) as exc:
                self.status.setText(str(exc))

    def accept(self):
        if not self._busy:
            if QImage(str(self.current_path)).isNull():
                self.status.setText("Không đọc được ảnh đã chọn. Hãy chọn phiên bản khác.")
                return
            super().accept()

    def reject(self):
        if self._busy:
            self.status.setText("Đang xử lý ảnh. Chờ hoàn tất trước khi đóng trình chỉnh sửa.")
        else:
            super().reject()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
            self.status.setText("Đang xử lý ảnh. Chờ hoàn tất trước khi đóng trình chỉnh sửa.")
        else:
            super().closeEvent(event)
