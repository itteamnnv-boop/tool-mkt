"""Offline visual editor tests: real Qt interaction, masks and mocked uploads."""
import base64
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from app import config
from app.ui.widgets.image_editor import ImageEditorDialog
from app.ui.video_tab import VideoTab, PROVIDER_GROK
from app.ui.image_tab import ImageTab


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.path = self.folder / "original.png"
        image = QImage(400, 300, QImage.Format.Format_ARGB32)
        image.fill(QColor("#ccbbaa"))
        image.save(str(self.path))
        for name, value in (("load_settings", dict(config.DEFAULT_SETTINGS)), ("save_settings", None),
                            ("get_secret", "fake"), ("output_dir", self.folder)):
            self.stack.enter_context(patch.object(config, name, return_value=value))
        self.stack.enter_context(patch("app.storage.history_store.add_image"))
        self.dialog = ImageEditorDialog(self.path)
        self.addCleanup(self.dialog.close)

    def wait_worker(self):
        for _ in range(300):
            QTest.qWait(10)
            if not self.dialog._busy and not self.dialog._worker.isRunning():
                QTest.qWait(20)
                return
        self.fail("Editor worker timed out")

    def test_drag_after_zoom_and_mask_coordinates(self):
        self.dialog.show()
        QTest.qWait(30)
        canvas = self.dialog.canvas
        canvas.zoom(1.5)
        start = canvas.mapFromScene(QPointF(180, 130))
        end = canvas.mapFromScene(QPointF(80, 50))
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas.viewport(), end)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(self.dialog.regions.count(), 1)
        rect = self.dialog.checked_regions()[0]
        self.assertAlmostEqual(rect.left(), 80, delta=2)
        self.assertAlmostEqual(rect.top(), 50, delta=2)
        mask = canvas.mask(self.dialog.checked_regions())
        self.assertEqual(mask.size(), canvas.image.size())
        self.assertEqual(mask.pixelColor(100, 70).alpha(), 0)
        self.assertEqual(mask.pixelColor(10, 10).alpha(), 255)
        self.dialog.regions.item(0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(self.dialog.checked_regions(), [])

    def test_masked_api_upload_targets_first_image_and_cleans_temp_files(self):
        self.dialog.face_path = self.path
        self.dialog.add_region(QRectF(40, 50, 70, 80))
        self.dialog.instruction.setPlainText("Change shirt to blue")
        files = []

        def edit(**kwargs):
            source, face = [f[1] for f in kwargs["image"]]
            self.assertEqual(kwargs["mask"][2], "image/png")
            mask = kwargs["mask"][1]
            files.extend([source, face, mask])
            self.assertEqual(Path(face.name), self.path)
            mask_image = QImage(mask.name)
            self.assertEqual(mask_image.size(), QImage(source.name).size())
            self.assertEqual(mask_image.pixelColor(50, 60).alpha(), 0)
            self.assertEqual(mask_image.pixelColor(5, 5).alpha(), 255)
            self.assertIn("ảnh 1", kwargs["prompt"])
            return SimpleNamespace(usage=None, data=[SimpleNamespace(b64_json=base64.b64encode(self.path.read_bytes()).decode())])

        with patch("app.core.image_client.OpenAI") as api:
            api.return_value.images.edit.side_effect = edit
            self.dialog._apply()
            self.assertFalse(self.dialog.use_btn.isEnabled())
            self.dialog.reject()
            self.assertTrue(self.dialog._busy)
            self.wait_worker()
        self.assertEqual(len(self.dialog.versions), 2)
        self.assertNotEqual(self.dialog.current_path, self.path)
        self.assertTrue(all(f.closed for f in files))
        self.assertFalse(Path(files[0].name).exists())
        self.assertIsNone(self.dialog._temp)
        self.dialog.history.setCurrentRow(0)
        self.assertEqual(self.dialog.current_path, self.path)

    def test_failed_edit_retains_selection_and_instruction(self):
        self.dialog.add_region(QRectF(10, 10, 20, 20))
        self.dialog.instruction.setPlainText("Warm lighting")
        with patch("app.core.image_client.OpenAI") as api:
            api.return_value.images.edit.side_effect = RuntimeError("Offline failure")
            self.dialog._apply()
            self.wait_worker()
        self.assertEqual(self.dialog.current_path, self.path)
        self.assertEqual(len(self.dialog.versions), 1)
        self.assertEqual(self.dialog.regions.count(), 1)
        self.assertEqual(self.dialog.instruction.toPlainText(), "Warm lighting")
        self.assertIsNone(self.dialog._temp)
        self.assertTrue(self.dialog.use_btn.isEnabled())

    def test_crop_makes_new_version_and_export(self):
        self.dialog.add_region(QRectF(20, 30, 100, 120))
        self.dialog._crop()
        image = QImage(str(self.dialog.current_path))
        self.assertEqual((image.width(), image.height()), (100, 120))
        self.assertEqual(QImage(str(self.path)).width(), 400)
        destination = self.folder / "export.jpg"
        with patch("app.ui.widgets.image_editor.QFileDialog.getSaveFileName", return_value=(str(destination), "")):
            self.dialog._export()
        self.assertFalse(QImage(str(destination)).isNull())

    def test_accept_editor_updates_only_selected_video_material(self):
        tab = VideoTab()
        tab.provider_combo.setCurrentIndex(tab.provider_combo.findData(PROVIDER_GROK))
        tab.set_reference_image(self.path)
        result = self.folder / "result.png"
        result.write_bytes(self.path.read_bytes())
        with patch("app.ui.video_tab.ImageEditorDialog") as factory:
            dialog = factory.return_value
            dialog.versions = [(self.path, "Original"), (result, "Edited")]
            dialog.current_path = result
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            tab._on_open_visual_editor()
        self.assertEqual(tab._reference_image_path, result)
        self.assertEqual(tab.asset_version_combo.count(), 2)
        tab.deleteLater()

    def test_image_tab_opens_file_and_accepts_editor_result(self):
        tab = ImageTab()
        with patch("app.ui.image_tab.QFileDialog.getOpenFileName", return_value=(str(self.path), "")), \
                patch("app.ui.image_tab.ImageEditorDialog") as factory:
            dialog = factory.return_value
            dialog.versions = [(self.path, "Original")]
            dialog.current_path = self.path
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            tab.edit_image_btn.click()
        self.assertEqual(tab._current_image_path, self.path)
        self.assertTrue(tab.to_video_btn.isEnabled())
        tab.deleteLater()

    def test_whole_image_edit_uses_no_mask(self):
        self.dialog.instruction.setPlainText("Change colors")
        with patch("app.core.image_client.OpenAI") as api:
            api.return_value.images.edit.return_value = SimpleNamespace(usage=None, data=[SimpleNamespace(
                b64_json=base64.b64encode(self.path.read_bytes()).decode())])
            self.dialog._apply()
            self.wait_worker()
            self.assertNotIn("mask", api.return_value.images.edit.call_args.kwargs)
        self.assertEqual(len(self.dialog.versions), 2)


if __name__ == "__main__":
    unittest.main()
