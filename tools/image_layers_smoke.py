"""AI layer analysis contract, local segmentation and editor integration (offline)."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import image_editor_smoke
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from app.core.image_layers import ImageLayer, ImageLayerClient, parse_objects, refine_layers


class LayerTests(image_editor_smoke.EditorTests):
    def layer(self, name="Áo xanh", rect=QRectF(80, 50, 100, 120)):
        mask = QImage(400, 300, QImage.Format.Format_ARGB32)
        mask.fill(Qt.GlobalColor.transparent)
        painter = QPainter(mask)
        painter.fillRect(rect, Qt.GlobalColor.white)
        painter.end()
        return ImageLayer(name, "Giữa ảnh, phía trên quần", mask, rect, int(rect.width() * rect.height()))

    def test_schema_rejects_bad_coordinates_and_empty_layers(self):
        for data in ({}, {"objects": []}, {"objects": [{"name": "bad", "polygons": [[[0, 0], [9999, 0], [0, 3]]]}]}):
            with self.assertRaises(ValueError):
                parse_objects(json.dumps(data))

    def test_vision_request_and_real_edge_refinement(self):
        image = QImage(str(self.path))
        painter = QPainter(image)
        painter.fillRect(100, 70, 140, 140, QColor("#0044dd"))
        painter.end()
        image.save(str(self.path))
        objects = {"objects": [{"name": "Blue shirt", "description": "Center upper part", "polygons": [
            [[225, 200], [625, 200], [625, 733], [225, 733]]]}]}
        with patch("app.core.image_layers.OpenAI") as api:
            api.return_value.chat.completions.create.return_value = SimpleNamespace(
                usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(objects)))])
            layers = ImageLayerClient("fake").analyze(self.path)
            request = api.return_value.chat.completions.create.call_args.kwargs
            self.assertTrue(request["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
            self.assertIn('"holes"', request["messages"][0]["content"][0]["text"])
            self.assertIn('"background"', request["messages"][0]["content"][0]["text"])
            self.assertEqual(request["model"], "gpt-5.4")
            self.assertEqual(request["reasoning_effort"], "high")
            self.assertEqual(request["messages"][0]["content"][1]["image_url"]["detail"], "original")
        self.assertEqual(len(layers), 1)
        self.assertTrue(layers[0].refined)
        self.assertTrue(layers[0].contains(QPointF(130, 100)))
        self.assertFalse(layers[0].contains(QPointF(91, 61)))
        self.assertEqual(layers[0].mask.size(), image.size())

    def test_click_selects_small_layer_and_brush_corrects_mask(self):
        body = self.layer("Body", QRectF(20, 20, 300, 260))
        shirt = self.layer()
        self.dialog._layers_done([body, shirt])
        self.dialog._pick_layer(QPointF(100, 80))
        self.assertEqual(self.dialog.regions.currentItem().text(), shirt.name)
        self.assertEqual(self.dialog.checked_regions(), [shirt])
        self.assertIn("x=80", self.dialog.layer_description.text())
        self.dialog._paint_layer(QPointF(100, 80), QPointF(110, 80), True)
        self.assertFalse(shirt.contains(QPointF(105, 80)))
        self.dialog._paint_layer(QPointF(100, 80), QPointF(110, 80), False)
        self.assertTrue(shirt.contains(QPointF(105, 80)))
        self.dialog._pick_layer(QPointF(30, 30))
        self.assertEqual(self.dialog.regions.currentItem().text(), "Body")

    def test_layer_prompt_position_and_preserved_outside_pixels(self):
        layer = self.layer()
        self.dialog._layers_done([layer])
        self.dialog._pick_layer(QPointF(100, 80))
        self.dialog.instruction.setPlainText("Change to red")
        output = self.folder / "generated.png"
        image = QImage(400, 300, QImage.Format.Format_ARGB32)
        image.fill(QColor("red"))
        image.save(str(output))
        with patch("app.ui.widgets.image_editor.ImageClient") as client:
            client.return_value.generate_image.return_value = output
            self.dialog._apply()
            self.wait_worker()
            prompt = client.return_value.generate_image.call_args.kwargs["prompt"]
            self.assertIn("Áo xanh", prompt)
            self.assertIn("x=80", prompt)
            self.assertIn("400×300", prompt)
        result = QImage(str(self.dialog.current_path))
        self.assertEqual(result.pixelColor(100, 80), QColor("red"))
        self.assertEqual(result.pixelColor(10, 10), QImage(str(self.path)).pixelColor(10, 10))
        self.assertEqual(self.dialog.regions.count(), 0)
        self.dialog.history.setCurrentRow(0)
        self.assertEqual(self.dialog.regions.count(), 1)

    def test_brush_updates_bounds_and_empty_layer_is_not_editable(self):
        layer = self.layer()
        self.dialog._layers_done([layer])
        self.dialog._pick_layer(QPointF(100, 80))
        self.dialog.brush_size.setValue(200)
        self.dialog._paint_layer(QPointF(125, 110), QPointF(130, 110), True)
        self.assertEqual(layer.area, 0)
        self.assertTrue(layer.rect.isEmpty())
        self.assertTrue(layer.cutout(self.dialog.canvas.image).isNull())
        self.dialog.instruction.setPlainText("Change shirt")
        with patch("app.ui.widgets.image_editor.ImageClient") as client:
            self.dialog._apply()
            client.return_value.generate_image.assert_not_called()
        self.assertIn("không còn điểm ảnh", self.dialog.status.text())

    def test_export_cutout_has_transparency_and_original_untouched(self):
        layer = self.layer()
        # remove one interior area, which must remain transparent in the exported cutout
        painter = QPainter(layer.mask)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(QRectF(80, 50, 15, 15), Qt.GlobalColor.transparent)
        painter.end()
        self.dialog._layers_done([layer])
        self.dialog._pick_layer(QPointF(110, 100))
        output = self.folder / "material.png"
        with patch("app.ui.widgets.image_editor.QFileDialog.getSaveFileName", return_value=(str(output), "")):
            self.dialog._export_layer()
        cutout = QImage(str(output))
        self.assertEqual((cutout.width(), cutout.height()), (100, 120))
        self.assertEqual(cutout.pixelColor(3, 3).alpha(), 0)
        self.assertEqual(cutout.pixelColor(50, 60).alpha(), 255)

    def test_analysis_failure_keeps_existing_layers(self):
        layer = self.layer()
        self.dialog._layers_done([layer])
        with patch("app.ui.widgets.image_editor.ImageLayerClient") as client:
            client.return_value.analyze.side_effect = RuntimeError("Vision unavailable")
            self.dialog._analyze_layers()
            self.wait_worker()
        self.assertEqual(self.dialog.regions.count(), 1)
        self.assertTrue(self.dialog.analyze_btn.isEnabled())

    def test_model_selection_is_saved_separately_from_content_model(self):
        from app import config
        self.assertEqual(self.dialog.layer_model.currentData(), "gpt-5.4")
        self.dialog.layer_model.setCurrentIndex(self.dialog.layer_model.findData("gpt-4o-mini"))
        with patch("app.ui.widgets.image_editor.ImageLayerClient") as client, patch.object(config, "save_settings") as save:
            client.return_value.analyze.return_value = [self.layer()]
            self.dialog._analyze_layers()
            self.wait_worker()
            client.assert_called_once_with("fake", "gpt-4o-mini")
            saved = save.call_args.args[0]
            self.assertEqual(saved["openai_layer_model"], "gpt-4o-mini")
            self.assertEqual(saved["openai_text_model"], config.DEFAULT_SETTINGS["openai_text_model"])

    def test_economy_model_does_not_receive_unsupported_options(self):
        with patch("app.core.image_layers.OpenAI") as api, patch("app.core.image_layers.refine_layers", return_value=[]):
            api.return_value.chat.completions.create.return_value = SimpleNamespace(
                usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"objects": [
                    {"name": "Test", "polygons": [[[0, 0], [100, 0], [100, 100]]]}]})))])
            ImageLayerClient("fake", "gpt-4o-mini").analyze(self.path)
            request = api.return_value.chat.completions.create.call_args.kwargs
            self.assertNotIn("reasoning_effort", request)
            self.assertEqual(request["messages"][0]["content"][1]["image_url"]["detail"], "high")

    def test_grok_routes_to_xai_and_records_grok_usage(self):
        with patch("app.core.image_layers.OpenAI") as api, patch("app.core.image_layers.refine_layers", return_value=[]), \
                patch("app.core.image_layers.history_store.add_token_usage") as usage:
            api.return_value.chat.completions.create.return_value = SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=123, completion_tokens=456),
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"objects": [
                    {"name": "Áo", "polygons": [[[0, 0], [100, 0], [100, 100]]]}]})))])
            ImageLayerClient("fake-xai", "grok-4.7").analyze(self.path)
            api.assert_called_once_with(api_key="fake-xai", base_url="https://api.x.ai/v1")
            request = api.return_value.chat.completions.create.call_args.kwargs
            self.assertEqual(request["model"], "grok-4.7")
            self.assertEqual(request["response_format"], {"type": "json_object"})
            self.assertNotIn("reasoning_effort", request)
            self.assertEqual(request["messages"][0]["content"][1]["image_url"]["detail"], "high")
            usage.assert_called_once_with("Grok", "grok-4.7", "phân tích lớp ảnh", 123, 456)

    def test_grok_selection_uses_only_grok_key(self):
        from app import config
        self.dialog.layer_model.setCurrentIndex(self.dialog.layer_model.findData("grok-4.7"))
        with patch.object(config, "get_secret", return_value="fake-xai") as secret, \
                patch("app.ui.widgets.image_editor.ImageLayerClient") as client:
            client.return_value.analyze.return_value = [self.layer()]
            self.dialog._analyze_layers()
            self.wait_worker()
            secret.assert_called_once_with("grok_api_key")
            client.assert_called_once_with("fake-xai", "grok-4.7")

    def test_missing_grok_key_keeps_layers(self):
        from app import config
        self.dialog._layers_done([self.layer()])
        self.dialog.layer_model.setCurrentIndex(self.dialog.layer_model.findData("grok-4.7"))
        with patch.object(config, "get_secret", return_value=""):
            self.dialog._analyze_layers()
        self.assertFalse(self.dialog._busy)
        self.assertEqual(self.dialog.regions.count(), 1)
        self.assertIn("Thiếu Grok API key", self.dialog.status.text())

    def test_click_empty_space_does_not_edit_previous_layer_or_whole_image(self):
        layer = self.layer()
        self.dialog._layers_done([layer])
        self.dialog._pick_layer(QPointF(100, 80))
        self.dialog._pick_layer(QPointF(390, 290))
        self.assertEqual(self.dialog.checked_regions(), [])
        self.assertIsNone(self.dialog.regions.currentItem())
        self.dialog.instruction.setPlainText("Change color")
        with patch("app.ui.widgets.image_editor.ImageClient") as client:
            self.dialog._apply()
            client.return_value.generate_image.assert_not_called()
        self.assertIn("Chưa chọn lớp", self.dialog.status.text())

    def test_holes_survive_refinement_and_background_excludes_subject(self):
        import numpy as np
        image = QImage(200, 200, QImage.Format.Format_ARGB32)
        image.fill(QColor("beige"))
        painter = QPainter(image)
        painter.fillRect(40, 30, 120, 140, QColor("black"))
        painter.fillRect(70, 65, 60, 70, QColor("pink"))
        painter.end()
        objects = parse_objects(json.dumps({"objects": [
            {"name": "Wall", "background": True, "polygons": [[[0, 0], [1000, 0], [1000, 1000], [0, 1000]]]},
            {"name": "Hair", "polygons": [[[190, 140], [810, 140], [810, 860], [190, 860]]],
             "holes": [[[345, 320], [655, 320], [655, 680], [345, 680]]]}
        ]}))
        layers = refine_layers(image, objects)
        wall, hair = layers
        self.assertFalse(hair.contains(QPointF(100, 100)))
        self.assertTrue(hair.contains(QPointF(50, 80)))
        self.assertTrue(wall.contains(QPointF(10, 10)))
        self.assertFalse(wall.contains(QPointF(50, 80)))
        arrays = [np.frombuffer(v.mask.bits(), np.uint8).reshape(200, 200, 4)[:, :, 3] > 0 for v in layers]
        self.assertFalse(np.any(arrays[0] & arrays[1]))

    def test_disconnected_material_keeps_small_piece(self):
        image = QImage(200, 200, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.fillRect(20, 20, 70, 140, QColor("blue"))
        painter.fillRect(145, 95, 8, 12, QColor("blue"))
        painter.end()
        objects = [{"name": "Pieces", "description": "", "polygons": [
            [[95, 95], [455, 95], [455, 805], [95, 805]],
            [[720, 470], [775, 470], [775, 545], [720, 545]]]}]
        layer = refine_layers(image, objects)[0]
        self.assertTrue(layer.contains(QPointF(45, 70)))
        self.assertTrue(layer.contains(QPointF(148, 100)))

    def test_overlapping_layers_are_disjoint_independent_of_order(self):
        import cv2
        image = QImage(200, 200, QImage.Format.Format_ARGB32)
        image.fill(QColor("gray"))
        objects = [
            {"name": "Large", "description": "", "polygons": [[[100, 100], [900, 100], [900, 900], [100, 900]]]},
            {"name": "Small", "description": "", "polygons": [[[400, 400], [600, 400], [600, 600], [400, 600]]]}
        ]
        # Force the documented fallback and verify it cannot create overlapping masks.
        with patch("cv2.grabCut", side_effect=cv2.error("failed")):
            first = {v.name: v for v in refine_layers(image, objects)}
            second = {v.name: v for v in refine_layers(image, objects[::-1])}
        for name in first:
            self.assertEqual(first[name].mask, second[name].mask)
            self.assertFalse(first[name].refined)
        self.assertTrue(first["Small"].contains(QPointF(100, 100)))
        self.assertFalse(first["Large"].contains(QPointF(100, 100)))


if __name__ == "__main__":
    unittest.main()
