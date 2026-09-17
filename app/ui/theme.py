"""Shared glass colors and surface opacity, including native Windows tint."""
from pathlib import Path
import os

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

GLASS_TINTS = {
    "light": ("Trắng — Light mode", "#ffffff", "#ffffff", "#008dba"),
    "black": ("Đen — Dark mode", "#000000", "#000000", "#a788f3"),
    "smoke": ("Xám khói — theo mẫu", "#716e69", "#d8d3c9", "#a788f3"),
    "pearl": ("Bạc ngọc trai", "#747b80", "#dce6e9", "#70cfcc"),
    "graphite": ("Than chì", "#41464f", "#b8c3d4", "#9aaff5"),
}
GLASS_STYLES = {"liquid": "Liquid Glass — tím / ngọc lam", "crystal": "Crystal Glass — cam / xanh bạc"}
DEFAULT_APPEARANCE = {"glass_style": "liquid", "glass_tint": "smoke", "glass_transparency": 100, "glass_outer_transparency": 100, "glass_blur": False}


def appearance_options(settings=None):
    settings = settings or {}
    style = settings.get("glass_style", "liquid")
    if not isinstance(style, str) or style not in GLASS_STYLES:
        style = "liquid"
    tint = settings.get("glass_tint", "smoke")
    if not isinstance(tint, str) or tint not in GLASS_TINTS:
        tint = "smoke"
    try:
        transparency = int(settings.get("glass_transparency", 100))
    except (TypeError, ValueError, OverflowError):
        transparency = 100
    try:
        outer_transparency = int(settings.get("glass_outer_transparency", 100))
    except (TypeError, ValueError, OverflowError):
        outer_transparency = 100
    return {"glass_style": style, "glass_tint": tint, "glass_transparency": max(0, min(100, transparency)),
            "glass_outer_transparency": max(0, min(100, outer_transparency)),
            "glass_blur": settings.get("glass_blur", False) is True}


def is_light_appearance(settings=None):
    options = appearance_options(settings)
    return options["glass_tint"] == "light" or (options["glass_style"] == "crystal" and options["glass_tint"] != "black")


def native_glass_tint(settings=None):
    options = appearance_options(settings)
    color = QColor(GLASS_TINTS[options["glass_tint"]][1])
    if options["glass_style"] == "crystal" and options["glass_tint"] not in {"black", "light"}:
        color = QColor({"smoke": "#e4ddd5", "pearl": "#dde6ed", "graphite": "#bccad5"}[options["glass_tint"]])
    return color.red(), color.green(), color.blue(), round(255 * (100 - options["glass_transparency"]) / 100)


def apply_theme(app: QApplication, settings=None):
    options = appearance_options(settings)
    _, base, surface, accent = GLASS_TINTS[options["glass_tint"]]
    dark = options["glass_tint"] == "black"
    light = options["glass_tint"] == "light"
    crystal = is_light_appearance(options)
    if crystal:
        base = {"smoke": "#e4ddd5", "pearl": "#dde6ed", "graphite": "#bccad5", "light": "#ffffff"}[options["glass_tint"]]
        surface, accent = ("#ffffff" if light else "#f2f6fc"), "#008dba"
    foreground, muted = ("#283744", "#526773") if crystal else ("#f4f4f0", "#c9c8c3")
    app.setProperty("glassStyle", "crystal" if crystal else "liquid")
    factor = (100 - options["glass_transparency"]) / 35

    def rgba(color, opacity):
        value = QColor(color)
        alpha = max(0, min(255, round(opacity * factor)))
        return f"rgba({value.red()},{value.green()},{value.blue()},{alpha})"

    def edge(color, opacity):
        value = QColor(color)
        return f"rgba({value.red()},{value.green()},{value.blue()},{opacity})"

    def glass(opacity):
        value = QColor(surface)
        alpha = round(255 * (100 - options["glass_transparency"]) / 100) if dark or light else max(8, round(opacity * factor))
        return f"rgba({value.red()},{value.green()},{value.blue()},{min(255, alpha)})"

    if not app.property("glassFusionInstalled"):
        app.setStyle("Fusion")
        app.setProperty("glassFusionInstalled", True)
    families = set(QFontDatabase.families())
    preferred = ("Segoe UI Variable Text", "Segoe UI", "Noto Sans", "Ubuntu Sans", "DejaVu Sans")
    family = next((name for name in preferred if name in families), app.font().family())
    font = QFont(family)
    font.setPixelSize(14)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.1)
    app.setFont(font)
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: QColor(0, 0, 0, 0),
        QPalette.ColorRole.WindowText: foreground,
        QPalette.ColorRole.Base: QColor(0, 0, 0, 0),
        QPalette.ColorRole.AlternateBase: QColor(0, 0, 0, 0),
        QPalette.ColorRole.Text: foreground,
        QPalette.ColorRole.Button: QColor(0, 0, 0, 0),
        QPalette.ColorRole.ButtonText: foreground,
        QPalette.ColorRole.Highlight: accent,
        QPalette.ColorRole.HighlightedText: "#ffffff" if crystal else "#25272b",
        QPalette.ColorRole.PlaceholderText: muted,
        QPalette.ColorRole.ToolTipBase: QColor(base).darker(145),
        QPalette.ColorRole.ToolTipText: foreground if crystal else "#fafaf6",
        QPalette.ColorRole.Link: accent if crystal else surface,
    }.items():
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    outer_color = QColor(base)
    outer_background = f"rgba({outer_color.red()},{outer_color.green()},{outer_color.blue()},{round(255 * (100 - options['glass_outer_transparency']) / 100)})"
    stylesheet = (Path(__file__).resolve().parents[1] / "resources" / "style.qss").read_text(encoding="utf-8")
    stylesheet += f"""
/* User-adjustable frosted surfaces. Popups retain an opaque base for legibility. */
QWidget#centralArea, QWidget#centralArea[glassFallback="true"] {{ background: {outer_background}; border: 0; }}
QWidget#sidebar {{ background: {glass(24)}; border-color: {edge('#ffffff', 45)}; }}
QWidget#contentShell {{ background: {glass(37)}; border-color: {edge('#ffffff', 48)}; }}
QWidget#glassTitleBar {{ background: {glass(22)}; border-color: {edge('#ffffff', 36)}; }}
QLabel#windowCaption {{ background: transparent; border: 0; padding: 0 6px; }}
QWidget#card, QWidget#metricCard, QWidget#quickPanel {{ background: {rgba(surface, 19)}; border-color: {edge('#ffffff', 32)}; }}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateTimeEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit {{ background: {rgba('#282827', 48)}; border-color: {edge('#ffffff', 29)}; selection-background-color: {accent}; selection-color: #25272b; }}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ background: {rgba('#282827', 72)}; border-color: {accent}; }}
QLineEdit#toolSearch {{ background: {rgba('#333332', 43)}; }}
QHeaderView::section {{ background: {rgba('#282827', 32)}; color: #f4f4f0; }}
QTableWidget#dashboardTable, QAbstractItemView {{ background: {rgba('#282827', 32)}; alternate-background-color: {rgba(surface, 14)}; }}
QScrollArea#rowList, QWidget#pageRow, QWidget#logWrapper, QWidget#timelineStep, QGroupBox, QTabWidget::pane, QTabBar::tab {{ background: {rgba(surface, 12)}; }}
QLabel#mediaPreview {{ background: {rgba(surface, 8)}; }}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QDateTimeEdit:disabled {{ background: {rgba(surface, 6)}; }}
QComboBox QAbstractItemView, QAbstractItemView#toolSearchPopup, QMenu, QMenuBar, QToolTip {{ background: {QColor(base).darker(135).name()}; }}
QDialog, QDialog#processingDialog {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {base}, stop:1 {QColor(base).darker(140).name()}); }}
QSlider::groove:horizontal {{ background: rgba(255,255,255,32); height: 5px; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #f6f5ef; border: 1px solid {accent}; width: 15px; margin: -6px 0; border-radius: 8px; }}
    """
    for metric, color in {"contents": "#e4bd9a", "images": "#a8cde2", "videos": "#c5b3db", "posts": "#add1bb"}.items():
        stylesheet += f"""
QWidget#metricCard[metric="{metric}"] {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {rgba(color, 30)}, stop:1 {rgba(surface, 10)}); border-color: {edge(color, 65)}; }}
QWidget#metricCard[metric="{metric}"] QLabel#metricValue {{ color: {color}; }}
"""
    if crystal:
        crystal_style = (Path(__file__).resolve().parents[1] / "resources" / "crystal.qss").read_text(encoding="utf-8")
        stylesheet += crystal_style.replace("@FIELD@", rgba("#ffffff", 48)).replace("@FOCUS@", rgba("#ffffff", 72))
    # Linux compositors do not expose Windows Acrylic. Give transparent controls a
    # readable backdrop; users with compositor blur can opt into desktop transparency.
    linux_desktop = app.platformName() in {"xcb", "wayland", "wayland-egl"}
    fallback = linux_desktop and os.environ.get("CLAUDE_STUDIO_TRANSPARENT") != "1"
    app.setProperty("glassLinuxFallback", fallback)
    if linux_desktop:
        stylesheet += '\n* { font-family: "Ubuntu Sans", "Ubuntu", "DejaVu Sans", sans-serif; }\n'
    if fallback:
        colors = ("#000000", "#000000", "#000000") if dark else (("#eee9e3", "#cddce7", "#e0e9ec") if crystal else ("#48434a", "#303a48", "#425551"))
        stylesheet += f"""
QWidget#centralArea, QWidget#centralArea[glassFallback="true"] {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {colors[0]}, stop:0.5 {colors[1]}, stop:1 {colors[2]});
    border: 0; border-radius: 28px;
}}
"""
    stylesheet += (Path(__file__).resolve().parents[1] / "resources" / "typography.qss").read_text(encoding="utf-8")
    stylesheet += f'\n* {{ font-family: "{family}"; }}\nQPlainTextEdit#logConsole {{ font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace; }}\n'
    app.setStyleSheet(stylesheet)
