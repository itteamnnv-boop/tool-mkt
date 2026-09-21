"""Appearance preview and saving, independent of credential settings."""
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from app import config
from app.ui.theme import BORDER_STYLES, DEFAULT_APPEARANCE, GLASS_STYLES, GLASS_TINTS, appearance_options, is_light_appearance
from app.ui.widgets.liquid_glass import GlassCard


class AppearancePanel(GlassCard):
    appearance_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)
        title = QLabel("Màu sắc, độ trong suốt & viền")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        style_row = QHBoxLayout()
        style_row.setSpacing(12)
        style_row.addWidget(QLabel("Phong cách"))
        self.style_combo = QComboBox()
        self.style_combo.setAccessibleName("Phong cách giao diện")
        for key, label in GLASS_STYLES.items():
            self.style_combo.addItem(label, key)
        style_row.addWidget(self.style_combo, 1)
        layout.addLayout(style_row)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(QLabel("Sắc kính"))
        self.tint_combo = QComboBox()
        for key, (label, *_) in GLASS_TINTS.items():
            self.tint_combo.addItem(label, key)
        row.addWidget(self.tint_combo, 1)
        row.addWidget(QLabel("Độ trong suốt"))
        self.transparency_slider = QSlider(Qt.Orientation.Horizontal)
        self.transparency_slider.setRange(0, 100)
        self.transparency_slider.setAccessibleName("Độ trong suốt của nền kính; 100% tương ứng opacity nền 0%")
        self.transparency_slider.setMinimumWidth(100)
        row.addWidget(self.transparency_slider, 1)
        self.percentage = QLabel()
        self.percentage.setFixedWidth(42)
        row.addWidget(self.percentage)
        layout.addLayout(row)
        outer_row = QHBoxLayout()
        outer_row.addWidget(QLabel("Độ trong suốt vùng ngoài"))
        self.outer_transparency_slider = QSlider(Qt.Orientation.Horizontal)
        self.outer_transparency_slider.setRange(0, 100)
        self.outer_transparency_slider.setAccessibleName("Độ trong suốt vùng ngoài")
        outer_row.addWidget(self.outer_transparency_slider, 1)
        self.outer_percentage = QLabel()
        self.outer_percentage.setFixedWidth(42)
        outer_row.addWidget(self.outer_percentage)
        layout.addLayout(outer_row)
        self.blur_checkbox = QCheckBox("Làm mờ nền Windows (bao gồm vùng ngoài)")
        layout.addWidget(self.blur_checkbox)
        note = QLabel("Vùng ngoài 100% và tắt làm mờ: nhìn xuyên hoàn toàn. Độ trong suốt kính điều chỉnh các khung bên trong.")
        note.setWordWrap(True)
        layout.addWidget(note)
        border_row = QHBoxLayout()
        border_row.addWidget(QLabel("Kiểu viền"))
        self.border_style_combo = QComboBox()
        self.border_style_combo.setAccessibleName("Kiểu viền hệ thống")
        for key, label in BORDER_STYLES.items():
            self.border_style_combo.addItem(label, key)
        border_row.addWidget(self.border_style_combo, 1)
        border_row.addWidget(QLabel("Độ dày"))
        self.border_width_spin = QDoubleSpinBox()
        self.border_width_spin.setRange(0.5, 4.0)
        self.border_width_spin.setSingleStep(0.5)
        self.border_width_spin.setDecimals(1)
        self.border_width_spin.setSuffix(" px")
        self.border_width_spin.setAccessibleName("Độ dày viền hệ thống")
        border_row.addWidget(self.border_width_spin)
        layout.addLayout(border_row)
        border_detail = QHBoxLayout()
        self.border_color_btn = QPushButton()
        self.border_color_btn.setAccessibleName("Chọn màu viền đơn sắc")
        self.border_color_btn.clicked.connect(self._choose_border_color)
        border_detail.addWidget(self.border_color_btn)
        border_detail.addWidget(QLabel("Độ rõ viền"))
        self.border_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.border_opacity_slider.setRange(0, 100)
        self.border_opacity_slider.setAccessibleName("Độ rõ viền hệ thống")
        border_detail.addWidget(self.border_opacity_slider, 1)
        self.border_percentage = QLabel()
        self.border_percentage.setFixedWidth(42)
        border_detail.addWidget(self.border_percentage)
        layout.addLayout(border_detail)
        actions = QHBoxLayout()
        self.hint = QLabel("Xem thay đổi ngay trên toàn bộ giao diện. Nền phía sau ảnh hưởng đến màu kính.")
        self.hint.setWordWrap(True)
        actions.addWidget(self.hint, 1)
        self.reset_btn = QPushButton("Mặc định")
        self.reset_btn.clicked.connect(self.reset)
        actions.addWidget(self.reset_btn)
        self.save_btn = QPushButton("Lưu giao diện")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self.save)
        actions.addWidget(self.save_btn)
        layout.addLayout(actions)
        self._set_values(appearance_options(config.load_settings()))
        self.tint_combo.currentIndexChanged.connect(self._preview)
        self.style_combo.currentIndexChanged.connect(self._preview)
        self.transparency_slider.valueChanged.connect(self._preview)
        self.outer_transparency_slider.valueChanged.connect(self._preview)
        self.blur_checkbox.toggled.connect(self._preview)
        self.border_style_combo.currentIndexChanged.connect(self._preview)
        self.border_width_spin.valueChanged.connect(self._preview)
        self.border_opacity_slider.valueChanged.connect(self._preview)

    def options(self):
        return {"glass_style": self.style_combo.currentData(), "glass_tint": self.tint_combo.currentData(), "glass_transparency": self.transparency_slider.value(),
                "glass_outer_transparency": self.outer_transparency_slider.value(), "glass_blur": self.blur_checkbox.isChecked(),
                "border_style": self.border_style_combo.currentData(), "border_width": self.border_width_spin.value(),
                "border_color": self._border_color, "border_opacity": self.border_opacity_slider.value()}

    def _set_values(self, options):
        self.style_combo.blockSignals(True)
        self.tint_combo.blockSignals(True)
        self.transparency_slider.blockSignals(True)
        self.outer_transparency_slider.blockSignals(True)
        self.blur_checkbox.blockSignals(True)
        for control in (self.border_style_combo, self.border_width_spin, self.border_opacity_slider):
            control.blockSignals(True)
        self.tint_combo.setCurrentIndex(self.tint_combo.findData(options["glass_tint"]))
        self.style_combo.setCurrentIndex(self.style_combo.findData(options["glass_style"]))
        self.transparency_slider.setValue(options["glass_transparency"])
        self.percentage.setText(f'{options["glass_transparency"]}%')
        self.outer_transparency_slider.setValue(options["glass_outer_transparency"])
        self.outer_percentage.setText(f'{options["glass_outer_transparency"]}%')
        self.blur_checkbox.setChecked(options["glass_blur"])
        self.border_style_combo.setCurrentIndex(self.border_style_combo.findData(options["border_style"]))
        self.border_width_spin.setValue(options["border_width"])
        self._border_color = options["border_color"]
        self.border_opacity_slider.setValue(options["border_opacity"])
        self._refresh_border_controls()
        for control in (self.border_style_combo, self.border_width_spin, self.border_opacity_slider):
            control.blockSignals(False)
        self.tint_combo.blockSignals(False)
        self.style_combo.blockSignals(False)
        self.transparency_slider.blockSignals(False)
        self.outer_transparency_slider.blockSignals(False)
        self.blur_checkbox.blockSignals(False)

    def _preview(self, *_):
        self._refresh_border_controls()
        self.percentage.setText(f"{self.transparency_slider.value()}%")
        self.outer_percentage.setText(f"{self.outer_transparency_slider.value()}%")
        self.hint.setText("Đang xem trước. Nhấn Lưu giao diện để dùng cho lần mở sau.")
        if is_light_appearance(self.options()):
            self.hint.setText("Kính pha lê dùng chữ tối, phù hợp nền sáng. Nhấn Lưu giao diện để dùng cho lần mở sau.")
        if self.tint_combo.currentData() == "light":
            self.hint.setText("Light mode dùng nền trắng và chữ tối. Nhấn Lưu giao diện để dùng cho lần mở sau.")
        if self.style_combo.currentData() == "basic":
            self.hint.setText("Basic dùng nút phẳng xanh dương, nút phụ dạng viền và bóng nhẹ. Nhấn Lưu giao diện để dùng cho lần mở sau.")
        self.appearance_changed.emit(self.options())

    def _refresh_border_controls(self):
        enabled = self.border_style_combo.currentData() != "none"
        self.border_width_spin.setEnabled(enabled)
        self.border_opacity_slider.setEnabled(enabled)
        self.border_color_btn.setEnabled(self.border_style_combo.currentData() == "solid")
        self.border_color_btn.setText("Màu viền: " + self._border_color.upper())
        self.border_percentage.setText(f"{self.border_opacity_slider.value()}%")

    def _choose_border_color(self):
        color = QColorDialog.getColor(QColor(self._border_color), self, "Chọn màu viền")
        if color.isValid():
            self._border_color = color.name()
            self._preview()

    def reset(self):
        self._set_values(DEFAULT_APPEARANCE)
        self._preview()

    def save(self):
        settings = config.load_settings()
        settings.update(self.options())
        config.save_settings(settings)
        self.hint.setText("Đã lưu phong cách, màu sắc, độ trong suốt và viền.")
        self.appearance_changed.emit(self.options())
