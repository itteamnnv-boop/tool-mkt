"""Offline UI regression check. Uses synthetic settings; never reads real credentials.

Run: .venv/Scripts/python.exe tools/ui_smoke.py
Screenshots: output/ui-review/<width>-<page>.png
"""
from __future__ import annotations

import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QScrollArea

from app import config
from app.ui.main_window import MainWindow
from run import apply_theme


def main() -> None:
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
        window = MainWindow()
        window.show()
        app.processEvents()

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
        assert not window.nav_group.isVisible()
        assert window.settings_btn.isVisible()
        window.group_btn.click()
        assert window.nav_group.isVisible()

        window.content_tab.log_message.emit("Kiểm tra nhật ký tập trung", "success")
        assert "Kiểm tra nhật ký" in window.log_console.toPlainText()
        window.log_tab.clear_btn.click()
        assert not window.log_console.toPlainText()
        window.automation_tab.settings_btn.click()
        assert window.stack.currentWidget().widget() is window.automation_settings_tab
        assert not any(isinstance(w, QDialog) and w.isVisible() for w in app.topLevelWidgets())

        output = ROOT / "output" / "ui-review"
        output.mkdir(parents=True, exist_ok=True)
        issues = []
        for width, height in [(1240, 840), (980, 680)]:
            window.resize(width, height)
            app.processEvents()
            assert window.width() == width and window.height() == height, window.size()
            for page in window._page_stack_index:
                window._show_page(page)
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
                window.grab().save(str(output / f"{width}-{page}.png"))
                scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                app.processEvents()
                for button in scroll.findChildren(type(window.settings_btn)):
                    if button.text().startswith("Lưu cài đặt"):
                        assert scroll.viewport().rect().contains(button.mapTo(scroll.viewport(), button.rect().center()))
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
        unexpected = [m for m in warnings if "propagateSizeHints" not in m]
        assert not unexpected, unexpected
        assert not issues, issues
        print("PASS: navigation, collapsible group, inline settings, shared log, 18 screen renders; no QSS/layout warnings or horizontal overflow.")


if __name__ == "__main__":
    main()
