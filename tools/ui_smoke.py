"""Offline UI regression check. Uses synthetic settings; never reads real credentials.

Run: .venv/Scripts/python.exe tools/ui_smoke.py
Screenshots: output/ui-review/<width>-<page>.png
Previews are composed on a synthetic backdrop; original alpha is tested separately.
"""
from __future__ import annotations

import os
import sys
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QScrollArea

from app import config
from app.core import windows_acrylic
from app.ui.main_window import MainWindow
from app.ui.widgets.glass_chrome import GlassTitleBar
from app.ui.widgets.appearance_panel import AppearancePanel
from app.ui.theme import DEFAULT_APPEARANCE, appearance_options, native_glass_tint
from app.core.content_prompts import SYSTEM_PROMPT_POST
from run import apply_theme


def save_review_snapshot(window, path):
    preview = QPixmap(window.size())
    painter = QPainter(preview)
    backdrop = QLinearGradient(0, 0, window.width(), window.height())
    colors = ("#f2f0ed", "#cbd5e1", "#e1ebef") if QApplication.instance().property("glassStyle") == "crystal" else ("#7b706d", "#3c4455", "#456669")
    backdrop.setColorAt(0, QColor(colors[0]))
    backdrop.setColorAt(0.45, QColor(colors[1]))
    backdrop.setColorAt(1, QColor(colors[2]))
    painter.fillRect(preview.rect(), backdrop)
    painter.drawPixmap(0, 0, window.grab())
    painter.end()
    preview.save(str(path))


def main() -> None:
    # Validate the native zero-tint path without changing any desktop window.
    native_calls = []

    def record_composition(hwnd, data):
        accent = data.contents.Data.contents
        native_calls.append((accent.AccentState, accent.GradientColor))
        return 1

    native_api = SimpleNamespace(user32=SimpleNamespace(SetWindowCompositionAttribute=record_composition))
    with patch.object(windows_acrylic.sys, "platform", "win32"), patch.object(windows_acrylic.ctypes, "windll", native_api, create=True):
        assert windows_acrylic.disable_window_blur(1)
        assert native_calls[-1] == (0, 0)
        assert windows_acrylic.enable_window_blur(1, 113, 110, 105, 0)
        assert native_calls[-1][0] == 3
        assert native_calls[-1][1] >> 24 == 0
        assert windows_acrylic.enable_window_blur(1, 113, 110, 105, 100)
        assert native_calls[-1][0] == 4
        assert native_calls[-1][1] >> 24 == 100
    warnings = []
    qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
    app = QApplication([])
    apply_theme(app)
    settings = dict(config.DEFAULT_SETTINGS)
    settings["facebook_pages"] = [{"id": "demo-page", "name": "Page minh hoạ"}]
    with ExitStack() as stack:
        stack.enter_context(patch.object(config, "load_settings", side_effect=lambda: dict(settings)))
        stack.enter_context(patch.object(config, "save_settings", side_effect=settings.update))
        stack.enter_context(patch.object(config, "get_secret", return_value=""))
        stack.enter_context(patch.object(config, "set_secret"))
        stack.enter_context(patch.object(config, "get_page_token", return_value="demo"))
        stack.enter_context(patch.object(config, "migrate_legacy_facebook_config"))
        stack.enter_context(patch("app.storage.history_store.init_db"))
        stack.enter_context(patch("app.storage.history_store.add_image"))
        stack.enter_context(patch("app.storage.history_store.list_recent", return_value=[]))
        stack.enter_context(patch("app.storage.history_store.list_contents", return_value=[]))
        stack.enter_context(patch("app.storage.history_store.list_scheduled_posts", return_value=[]))
        stack.enter_context(patch("app.storage.history_store.list_successful_posts", return_value=[]))
        stack.enter_context(patch("app.storage.history_store.dashboard_stats", return_value={
            "totals": {"contents": 25, "images": 0, "videos": 4, "posts": 8},
            "today": {"contents": 0, "images": 0, "videos": 0, "posts": 4},
            "input_tokens": 0, "output_tokens": 0, "token_requests": 0, "providers": [],
        }))
        window = MainWindow()
        window.show()
        app.processEvents()

        # Closing progress only hides it; the toolbar next to the account restores it.
        progress = window.image_tab.processing_dialog
        progress.start("Đang tạo ảnh thử nghiệm")
        progress.close()
        assert not window.task_indicator.isHidden()
        window.task_indicator.click()
        assert progress.isVisible() and progress.scene.running
        progress.finish("Hoàn tất")
        window.task_indicator.click()
        assert progress.isVisible() and not progress.scene.running
        progress.reject()
        assert window.task_indicator.isHidden()

        # Archived content opens a reusable copy and navigates to each destination.
        assert window.nav_key_group["archive"] == "creation"
        window.archive_tab.reuse_requested.emit("content", "Saved topic", "Saved text\n#tag")
        assert window.stack.currentWidget().widget() is window.content_tab
        assert window.content_tab.topic_input.text() == "Saved topic"
        assert window.content_tab.result_text.toPlainText() == "Saved text\n#tag"
        for destination in ("image", "video"):
            window.archive_tab.reuse_requested.emit(destination, "Saved topic", "Saved text\n#tag")
            target = getattr(window, destination + "_tab")
            assert window.stack.currentWidget().widget() is target
            assert target._content_context == "Saved text\n#tag"
        window.archive_tab.reuse_requested.emit("facebook", "Saved topic", "Saved text\n#tag")
        assert window.stack.currentWidget().widget() is window.facebook_tab

        # A user must be able to return to the same tool after visiting settings.
        window.nav_buttons["image"].click()
        window.settings_btn.click()
        assert window.stack.currentWidget().widget() is window.settings_tab
        window.settings_tab.save_btn.click()
        assert "đã được lưu" in window.settings_tab.status_label.text()
        window.nav_buttons["image"].click()
        assert window.stack.currentWidget().widget() is window.image_tab

        # Collapsing the group must not remove settings or lose the current page.
        window.group_btn.click()
        assert window.nav_group.isVisible()
        assert window.sidebar.width() == 64
        assert not window.nav_buttons["content"].text()
        assert settings["sidebar_expanded"] is False
        assert window.settings_btn.isVisible()
        window.group_btn.click()
        assert window.nav_group.isVisible()
        assert window.sidebar.width() == 224
        assert window.nav_buttons["content"].text() == window.nav_buttons["content"].toolTip()
        assert settings["sidebar_expanded"] is True

        # Sections can collapse independently; compact mode keeps all tools reachable.
        window.nav_group_headers["creation"].click()
        assert not window.nav_buttons["content"].isVisible()
        assert settings["sidebar_groups"]["creation"] is False
        window.group_btn.click()
        assert window.nav_buttons["content"].isVisible()
        window.group_btn.click()
        assert not window.nav_buttons["content"].isVisible()
        window._show_page("image")
        assert window.nav_group_headers["creation"].isChecked()
        assert window.nav_buttons["content"].isVisible()
        assert settings["sidebar_groups"]["creation"] is True

        # Every tool remains reachable from the compact reference-style toolbar.
        for action in window.more_button.menu().actions():
            action.trigger()
            key = next(key for key, label in window.page_labels.items() if label == action.text())
            expected = window.log_tab if key == "logs" else getattr(window, key + "_tab")
            assert window.stack.currentWidget().widget() is expected
            assert window.more_button.isChecked()
        window._open_search_result("Tạo Ảnh")
        assert window.stack.currentWidget().widget() is window.image_tab
        window._open_search_result("Cài đặt tự động hoá")
        assert window.stack.currentWidget().widget() is window.automation_settings_tab
        window.shortcut_buttons["dashboard"].click()
        assert window.stack.currentWidget().widget() is window.dashboard_tab
        window.dashboard_tab.page_requested.emit("content")
        assert window.stack.currentWidget().widget() is window.content_tab
        chrome = window.findChild(GlassTitleBar)
        chrome.toggle_maximized()
        app.processEvents()
        assert window.isMaximized()
        chrome.toggle_maximized()
        app.processEvents()
        assert not window.isMaximized()

        # Appearance preview, persistence and reset must leave credentials untouched.
        appearance = window.settings_tab.appearance_panel
        appearance.tint_combo.setCurrentIndex(appearance.tint_combo.findData("light"))
        appearance.transparency_slider.setValue(0)
        app.processEvents()
        assert window._appearance["glass_tint"] == "light"
        assert app.property("glassStyle") == "crystal"
        assert app.palette().color(app.palette().ColorRole.Text).lightness() < 100
        assert native_glass_tint(window._appearance) == (255, 255, 255, 255)
        appearance.save_btn.click()
        restored_light = AppearancePanel()
        assert restored_light.options() == appearance.options()
        restored_light.deleteLater()
        appearance.reset_btn.click()
        appearance.style_combo.setCurrentIndex(appearance.style_combo.findData("crystal"))
        app.processEvents()
        assert window._appearance["glass_style"] == "crystal"
        assert app.palette().color(app.palette().ColorRole.Text).lightness() < 100
        appearance.tint_combo.setCurrentIndex(appearance.tint_combo.findData("pearl"))
        app.processEvents()
        assert window._appearance["glass_tint"] == "pearl"
        appearance.transparency_slider.setValue(30)
        opaque_style = app.styleSheet()
        opaque_alpha = native_glass_tint(window._appearance)[3]
        appearance.transparency_slider.setValue(85)
        app.processEvents()
        assert app.styleSheet() != opaque_style
        assert native_glass_tint(window._appearance)[3] < opaque_alpha
        appearance.outer_transparency_slider.setValue(45)
        appearance.blur_checkbox.setChecked(True)
        app.processEvents()
        assert window._appearance["glass_outer_transparency"] == 45
        assert window._appearance["glass_blur"] is True
        assert window.grab().toImage().pixelColor(5, window.height() // 2).alpha() == round(255 * .55)
        appearance.border_style_combo.setCurrentIndex(appearance.border_style_combo.findData("none"))
        app.processEvents()
        assert app.property("border_style") == "none"
        assert not appearance.border_width_spin.isEnabled()
        assert not appearance.border_color_btn.isEnabled()
        appearance.border_style_combo.setCurrentIndex(appearance.border_style_combo.findData("solid"))
        appearance.border_width_spin.setValue(3.0)
        appearance.border_opacity_slider.setValue(65)
        with patch("app.ui.widgets.appearance_panel.QColorDialog.getColor", return_value=QColor("#12abef")):
            appearance.border_color_btn.click()
        app.processEvents()
        assert window._appearance["border_style"] == "solid"
        assert window._appearance["border_width"] == 3.0
        assert window._appearance["border_color"] == "#12abef"
        assert window._appearance["border_opacity"] == 65
        with patch.object(config, "set_secret") as secrets:
            appearance.save_btn.click()
            secrets.assert_not_called()
        assert settings["glass_transparency"] == 85
        assert settings["glass_tint"] == "pearl"
        assert settings["glass_style"] == "crystal"
        assert settings["glass_outer_transparency"] == 45
        assert settings["glass_blur"] is True
        assert settings["border_color"] == "#12abef"
        assert settings["border_width"] == 3.0
        assert settings["border_opacity"] == 65
        assert settings["facebook_pages"][0]["id"] == "demo-page"
        restored = AppearancePanel()
        assert restored.options() == appearance.options()
        restored.deleteLater()
        appearance.reset_btn.click()
        appearance.save_btn.click()
        app.processEvents()
        assert window._appearance == DEFAULT_APPEARANCE
        assert native_glass_tint(window._appearance)[3] == 0
        assert appearance_options({"glass_tint": [], "glass_transparency": "invalid"}) == window._appearance
        assert appearance_options({"glass_transparency": 150})["glass_transparency"] == 100
        assert appearance_options({"glass_style": "unknown"})["glass_style"] == "liquid"
        invalid_border = appearance_options({"border_style": [], "border_width": float("nan"), "border_color": [], "border_opacity": "invalid"})
        assert invalid_border == DEFAULT_APPEARANCE
        assert appearance_options({"border_width": 99, "border_opacity": -1})["border_width"] == 4
        assert appearance_options({"border_opacity": -1})["border_opacity"] == 0
        window._show_page("content")
        app.processEvents()
        rendered = window.grab().toImage()
        assert rendered.pixelColor(5, window.height() // 2).alpha() == 0, "Opaque root background"
        # Inspect actual pixels in an empty card, rather than just QSS declarations.
        card = window.settings_tab.appearance_panel
        window._show_page("settings")
        window.stack.currentWidget().verticalScrollBar().setValue(0)
        app.processEvents()
        rendered = window.grab().toImage()
        # Sample inside the clear body, away from the new rounded reflective rim.
        blank = card.mapTo(window, QPoint(12, card.height() - 22))
        assert rendered.pixelColor(blank).alpha() <= 10, "Opaque nested card background"

        # Inspect the expanded prompt editor without reading the user's actual DB.
        window._show_page("content")
        window.resize(980, 680)
        prompt_editor = window.content_tab.prompt_editor
        with patch("app.ui.widgets.post_prompt_editor.get_post_system_prompt", return_value=SYSTEM_PROMPT_POST):
            prompt_editor.toggle_btn.setChecked(True)
            for _ in range(100):
                QTest.qWait(20)
                if not prompt_editor.busy:
                    break
            assert not prompt_editor.busy
            assert prompt_editor.editor.toPlainText() == SYSTEM_PROMPT_POST
            assert window.stack.currentWidget().horizontalScrollBar().maximum() == 0
            window.stack.currentWidget().ensureWidgetVisible(prompt_editor.editor)
            app.processEvents()
            prompt_snapshot = ROOT / "output" / "ui-review" / "980-content-prompt.png"
            prompt_snapshot.parent.mkdir(parents=True, exist_ok=True)
            save_review_snapshot(window, prompt_snapshot)
            prompt_editor.toggle_btn.setChecked(False)
            app.processEvents()

        # Ubuntu desktop fallback must stay readable, with explicit transparency opt-in.
        with patch.object(QApplication, "platformName", return_value="xcb"):
            with patch.dict(os.environ, {"CLAUDE_STUDIO_TRANSPARENT": "0"}):
                for style in ("liquid", "crystal", "basic"):
                    window.apply_appearance({**DEFAULT_APPEARANCE, "glass_style": style})
                    app.processEvents()
                    assert app.property("glassLinuxFallback")
                    pixel = window.grab().toImage().pixelColor(5, window.height() // 2)
                    assert pixel.alpha() == 255, "Ubuntu fallback is unreadable/transparent"
                    save_review_snapshot(window, ROOT / "output" / "ui-review" / f"ubuntu-{style}-settings.png")
            with patch.dict(os.environ, {"CLAUDE_STUDIO_TRANSPARENT": "1"}):
                window.apply_appearance(DEFAULT_APPEARANCE)
                app.processEvents()
                assert not app.property("glassLinuxFallback")
                assert window.grab().toImage().pixelColor(5, window.height() // 2).alpha() == 0
        window.apply_appearance(DEFAULT_APPEARANCE)

        window.content_tab.log_message.emit("Kiểm tra nhật ký tập trung", "success")
        assert "Kiểm tra nhật ký" in window.log_console.toPlainText()
        window.log_tab.clear_btn.click()
        assert not window.log_console.toPlainText()
        window.automation_tab.settings_btn.click()
        assert window.stack.currentWidget().widget() is window.automation_settings_tab
        assert not any(isinstance(w, QDialog) and w.isVisible() for w in app.topLevelWidgets())
        window.toast.hide()

        output = ROOT / "output" / "ui-review"
        output.mkdir(parents=True, exist_ok=True)
        issues = []
        for glass_style in ("liquid", "crystal", "basic"):
            appearance.style_combo.setCurrentIndex(appearance.style_combo.findData(glass_style))
            app.processEvents()
            style_suffix = f"-{glass_style}" if glass_style != "liquid" else ""
            for width, height in [(1240, 840), (980, 680)]:
                window.resize(width, height)
                app.processEvents()
                assert window.width() == width and window.height() == height, window.size()
                assert window.sidebar.width() == (224 if width >= 1140 else 64)
                # Exercise visible sidebar controls, including tools previously hidden.
                for key, button in window.nav_buttons.items():
                    window.nav_scroll.ensureWidgetVisible(button)
                    app.processEvents()
                    assert button.isVisible(), (width, key, "hidden sidebar control")
                    viewport = window.nav_scroll.viewport()
                    center = button.mapTo(viewport, button.rect().center())
                    assert viewport.rect().contains(center), (width, key, "unreachable sidebar control")
                    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                    app.processEvents()
                    assert window.stack.currentIndex() == window._page_stack_index[key]
                window.nav_scroll.verticalScrollBar().setValue(0)
                for page in window._page_stack_index:
                    window._show_page(page)
                    window.stack.currentWidget().verticalScrollBar().setValue(0)
                    for _ in range(3):
                        app.processEvents()
                    scroll = window.stack.currentWidget()
                    if scroll.horizontalScrollBar().maximum() > 0:
                        issues.append(f"{width}/{page}: horizontal overflow {scroll.horizontalScrollBar().maximum()}")
                    for nested in scroll.findChildren(QScrollArea):
                        if nested.isVisible() and nested.horizontalScrollBar().maximum() > 0:
                            issues.append(f"{width}/{page}: nested horizontal overflow")
                    header = scroll.widget().findChild(QLabel, "pageHeader")
                    assert header.height() <= header.sizeHint().height() + 4, (page, header.height())
                    save_review_snapshot(window, output / f"{width}{style_suffix}-{page}.png")
                    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                    app.processEvents()
                    for button in scroll.findChildren(type(window.settings_btn)):
                        if button.text().startswith("Lưu cài đặt"):
                            assert scroll.viewport().rect().contains(button.mapTo(scroll.viewport(), button.rect().center()))
        appearance.reset_btn.click()
        app.processEvents()
        fixture = QPixmap(640, 360)
        fixture.fill(QColor("#2dbac5"))
        fixture_path = output / "preview-fixture.png"
        fixture.save(str(fixture_path))
        window._show_page("image")
        window.image_tab._on_done("Test preview", fixture_path)
        for width, height in [(1240, 840), (980, 680)]:
            window.resize(width, height)
            app.processEvents()
            preview = window.image_tab.preview_label
            assert not preview.pixmap().isNull(), "Image disappeared after completion"
            assert preview.pixmap().width() <= preview.width()
            assert preview.pixmap().height() <= preview.height()
        window._show_page("automation_settings")
        window.automation_settings_tab.attachment_combo.setCurrentIndex(2)
        assert window.automation_settings_tab.avatar_combo.isEnabled()
        window.close()
        app.processEvents()
        # Offscreen Qt cannot raise the restored progress window; native platforms can.
        unexpected = [m for m in warnings if "propagateSizeHints" not in m
                      and not (app.platformName() == "offscreen" and m == "This plugin does not support raise()")]
        assert not unexpected, unexpected
        assert not issues, issues
        print("PASS: appearance preview/save/restore/reset, navigation, toolbar search/menu, window maximize/restore, inline settings, shared log, all pages at both sizes; no QSS/layout warnings or horizontal overflow.")


if __name__ == "__main__":
    main()
