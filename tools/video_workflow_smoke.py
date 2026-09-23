"""Offline checks for material preparation and image-to-video handoff."""
import os
import base64
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import config
from app.core.image_client import ImageClient
from app.ui.video_tab import VideoTab, PROVIDER_GROK, PROVIDER_HEYGEN


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for name, value in [("load_settings", dict(config.DEFAULT_SETTINGS)),
                            ("save_settings", None), ("get_secret", "fake"),
                            ("output_dir", self.folder)]:
            self.stack.enter_context(patch.object(config, name, return_value=value))
        self.stack.enter_context(patch("app.ui.video_tab.history_store.add_image"))
        self.stack.enter_context(patch("app.ui.video_tab.history_store.add_video"))
        self.tab = VideoTab()
        self.stack.enter_context(patch.object(self.tab.processing_dialog, "track"))
        self.tab.provider_combo.setCurrentIndex(self.tab.provider_combo.findData(PROVIDER_GROK))
        self.tab.script_input.setPlainText("Camera moves through the garden")
        self.tab.scene_input.setPlainText("Warm morning light")
        self.image = self.folder / "scene.png"
        pixmap = QPixmap(80, 60)
        pixmap.fill()
        pixmap.save(str(self.image))

    def wait_worker(self):
        for _ in range(300):
            QTest.qWait(10)
            if not self.tab._worker.isRunning() and not self.tab._asset_busy:
                QTest.qWait(20)
                return
        self.fail("Worker timed out")

    def test_prompt_creation_keeps_script_and_heygen_uses_agent(self):
        self.tab.provider_combo.setCurrentIndex(self.tab.provider_combo.findData(PROVIDER_HEYGEN))
        script = self.tab.script_input.toPlainText()
        with patch("app.ui.video_tab.get_text_client") as text_client:
            text_client.return_value._complete.return_value = "Friendly presenter, warm light"
            self.tab.create_prompt_btn.click()
            self.wait_worker()
        self.assertEqual(self.tab.script_input.toPlainText(), script)
        self.assertIn("Friendly presenter", self.tab.video_prompt_input.toPlainText())
        self.tab.avatar_combo.addItem("My avatar", "avatar-id")
        self.tab.voice_combo.addItem("My voice", "voice-id")
        with patch.object(self.tab, "_make_heygen_client") as client:
            client.return_value.generate_from_prompt_and_wait.return_value = self.folder / "agent.mp4"
            self.tab.generate_btn.click()
            self.wait_worker()
            args = client.return_value.generate_from_prompt_and_wait.call_args.kwargs
            self.assertEqual(args["avatar_id"], "avatar-id")
            self.assertEqual(args["voice_id"], "voice-id")
            self.assertEqual(args["script_text"], script)
            self.assertIn(script, args["prompt"])
            self.assertIn("Friendly presenter", args["prompt"])
            client.return_value.generate_and_wait.assert_not_called()

    def test_prompt_failure_preserves_previous_and_stale_prompt_blocks_render(self):
        self.tab.video_prompt_input.setPlainText("Keep previous prompt")
        with patch("app.ui.video_tab.get_text_client") as client:
            client.return_value._complete.return_value = ""
            self.tab.create_prompt_btn.click()
            self.wait_worker()
        self.assertEqual(self.tab.video_prompt_input.toPlainText(), "Keep previous prompt")
        self.assertTrue(self.tab.generate_btn.isEnabled())
        self.tab._prompt_source = self.tab._video_prompt_source()
        self.tab.script_input.setPlainText("Changed script")
        with patch.object(self.tab, "_on_generate_grok") as generate:
            self.tab._on_generate()
            generate.assert_not_called()

    def test_grok_receives_edited_prompt_and_materials(self):
        self.tab.set_reference_image(self.image)
        self.tab.video_prompt_input.setPlainText("Close up then slow pan")
        self.tab.next_step_btn.click()
        self.tab.script_next_btn.click()
        self.assertIn("Close up", self.tab.script_review.toPlainText())
        with patch.object(self.tab, "_make_grok_client") as client:
            client.return_value.generate_and_wait.return_value = self.folder / "grok.mp4"
            self.tab.generate_btn.click()
            self.wait_worker()
            args = client.return_value.generate_and_wait.call_args.kwargs
            self.assertIn("Close up then slow pan", args["prompt"])
            self.assertIn(self.tab.script_input.toPlainText(), args["prompt"])
            self.assertEqual(args["image_path"], self.image)

    def test_product_source_only_reaches_image_generation(self):
        with patch("app.ui.video_tab.QFileDialog.getOpenFileName", return_value=(str(self.image), "")):
            self.tab.attach_product_btn.click()
        self.assertEqual(self.tab._product_image_path, self.image)
        self.assertIsNone(self.tab.preview_asset_selector.currentData())
        self.assertFalse(self.tab.next_step_btn.isEnabled())
        self.assertFalse(self.tab._validate_materials())
        output = self.folder / "generated.png"
        output.write_bytes(self.image.read_bytes())
        with patch("app.ui.video_tab.ImageClient") as client:
            client.return_value.generate_image.return_value = output
            self.tab.generate_asset_btn.click()
            self.wait_worker()
            args = client.return_value.generate_image.call_args.kwargs
            self.assertEqual(args["product_image_path"], self.image)
            self.assertIn("Ảnh 1 là sản phẩm chính", args["prompt"])
        # The source files are no longer needed once the material has been made.
        self.tab._asset_face_path = self.image
        self.tab._asset_sample_path = self.image
        self.image.unlink()
        self.assertTrue(self.tab._validate_materials())
        self.tab.next_step_btn.click()
        self.assertNotIn(self.image.name, self.tab.material_summary.text())
        self.assertIn(output.name, self.tab.material_summary.text())
        self.tab.script_next_btn.click()
        with patch.object(self.tab, "_make_grok_client") as client:
            client.return_value.generate_and_wait.return_value = self.folder / "video.mp4"
            self.tab.generate_btn.click()
            self.wait_worker()
            args = client.return_value.generate_and_wait.call_args.kwargs
            self.assertEqual(args["image_path"], output)
            self.assertIsNone(args["reference_image_paths"])
            self.assertNotIn("Ảnh tham chiếu 1 là sản phẩm chính", args["prompt"])
        self.tab.clear_product_btn.click()
        self.assertIsNone(self.tab._product_image_path)
        self.assertEqual(self.tab._reference_image_path, output)

    def test_product_limit_invalid_file_and_busy(self):
        with patch("app.ui.video_tab.QFileDialog.getOpenFileName", return_value=(str(self.image), "")):
            self.tab._material_image_paths = [self.folder / f"ref{i}.png" for i in range(4)]
            self.tab.attach_product_btn.click()
            self.assertEqual(self.tab._product_image_path, self.image)
            self.tab._material_image_paths.clear()
            self.tab.attach_product_btn.click()
        self.tab._set_workflow_busy(True)
        self.tab._on_clear_product()
        self.assertEqual(self.tab._product_image_path, self.image)
        self.tab._set_workflow_busy(False)
        self.image.unlink()
        self.assertFalse(self.tab._validate_materials())
        with patch("app.ui.video_tab.ImageClient") as client:
            self.tab.generate_asset_btn.click()
            client.assert_not_called()

    def test_product_upload_order_with_face_and_scene(self):
        paths = [self.folder / name for name in ("face.png", "sample.png", "product.png")]
        for path in paths:
            path.write_bytes(self.image.read_bytes())
        with patch("app.core.image_client.OpenAI") as api:
            def edit(**kwargs):
                self.assertEqual([Path(f[1].name) for f in kwargs["image"]], paths)
                return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(self.image.read_bytes()).decode())], usage=None)
            api.return_value.images.edit.side_effect = edit
            ImageClient("fake").generate_image("Product scene", "1024x1024", self.folder,
                                               face_image_path=paths[0], reference_image_path=paths[1],
                                               product_image_path=paths[2])
            api.return_value.images.generate.assert_not_called()

    def test_generate_assets_then_video_handoff(self):
        self.tab.script_input.clear()
        with patch("app.ui.video_tab.ImageClient") as image_client:
            image_client.return_value.generate_image.return_value = self.image
            self.tab._on_generate_asset()
            self.assertFalse(self.tab.provider_combo.isEnabled())
            self.wait_worker()
            self.assertEqual(self.tab._reference_image_path, self.image)
            self.assertEqual(self.tab.workflow_stack.currentIndex(), 0)
            self.assertIn("Warm morning light", image_client.return_value.generate_image.call_args.kwargs["prompt"])
            self.tab.asset_role_combo.setCurrentIndex(1)
            self.tab._on_generate_asset()
            self.wait_worker()
            self.assertEqual(self.tab._material_image_paths, [self.image])
        self.tab.next_step_btn.click()
        self.assertEqual(self.tab.workflow_stack.currentIndex(), 1)
        self.tab.script_input.setPlainText("Camera moves through the garden")
        self.tab.script_next_btn.click()
        self.assertEqual(self.tab.workflow_stack.currentIndex(), 2)
        with patch.object(self.tab, "_make_grok_client") as client:
            client.return_value.generate_and_wait.return_value = self.folder / "video.mp4"
            self.tab.generate_btn.click()
            self.wait_worker()
            args = client.return_value.generate_and_wait.call_args.kwargs
            self.assertEqual(args["image_path"], self.image)
            self.assertEqual(args["reference_image_paths"], [self.image])
            self.assertIn("Camera moves", args["prompt"])
            self.assertIn("Warm morning light", args["prompt"])
            self.assertTrue(self.tab.grok_options.isEnabled())

    def test_missing_and_deleted_materials_block_generation(self):
        with patch.object(self.tab, "_make_grok_client") as client:
            self.tab._on_next_step()
            self.assertEqual(self.tab.workflow_stack.currentIndex(), 0)
            self.tab._on_generate_grok()
            self.tab.set_reference_image(self.image)
            self.image.unlink()
            self.tab._on_generate_grok()
            client.assert_not_called()

    def test_asset_failure_keeps_previous_materials_and_allows_retry(self):
        self.tab.set_reference_image(self.image)
        with patch("app.ui.video_tab.ImageClient") as client:
            client.return_value.generate_image.side_effect = RuntimeError("Offline failure")
            self.tab._on_generate_asset()
            self.wait_worker()
        self.assertEqual(self.tab._reference_image_path, self.image)
        self.assertTrue(self.tab.generate_asset_btn.isEnabled())
        self.assertFalse(self.tab.script_input.isReadOnly())
        self.assertIn("Offline failure", self.tab.status_caption.text())

    def test_reference_limit_and_heygen_route(self):
        self.tab._material_image_paths = [self.image] * 4
        self.tab.asset_role_combo.setCurrentIndex(1)
        with patch("app.ui.video_tab.ImageClient") as client:
            self.tab._on_generate_asset()
            client.assert_not_called()
        self.tab.provider_combo.setCurrentIndex(self.tab.provider_combo.findData(PROVIDER_HEYGEN))
        self.assertTrue(self.tab.grok_options.isHidden())
        self.assertFalse(self.tab.generate_btn.isHidden())
        with patch.object(self.tab, "_on_generate_heygen") as generate:
            self.tab._on_generate()
            generate.assert_called_once()

    def test_sequential_navigation_and_return_preserve_inputs(self):
        self.tab.script_input.clear()
        self.assertEqual(self.tab.workflow_stack.currentWidget(), self.tab.preparation_page)
        self.assertFalse(self.tab.next_step_btn.isEnabled())
        self.tab._on_next_step()
        self.assertEqual(self.tab.workflow_stack.currentIndex(), 0)
        self.assertFalse(self.tab.validation_hint.isHidden())
        self.tab._go_to_step(2)
        self.assertEqual(self.tab.workflow_stack.currentIndex(), 0)
        self.tab.set_reference_image(self.image)
        self.assertTrue(self.tab.next_step_btn.isEnabled())
        self.tab.next_step_btn.click()
        self.assertEqual(self.tab.workflow_stack.currentWidget(), self.tab.script_page)
        self.assertFalse(self.tab.script_next_btn.isEnabled())
        self.assertTrue(self.tab.generate_btn.isHidden())
        self.assertEqual(self.tab.preview_stack.currentWidget(), self.tab.asset_preview)
        self.tab._on_script_next()
        self.assertEqual(self.tab.workflow_stack.currentIndex(), 1)
        self.tab.script_input.setPlainText("A new script")
        self.tab.script_next_btn.click()
        self.assertEqual(self.tab.workflow_stack.currentIndex(), 2)
        self.assertIn("A new script", self.tab.script_review.toPlainText())
        self.assertIn("Warm morning light", self.tab.script_review.toPlainText())
        self.tab.back_step_btn.click()
        self.assertEqual(self.tab.workflow_stack.currentWidget(), self.tab.script_page)
        self.tab.back_material_btn.click()
        self.assertEqual(self.tab.workflow_stack.currentIndex(), 0)
        self.assertEqual(self.tab.script_input.toPlainText(), "A new script")
        self.assertEqual(self.tab._reference_image_path, self.image)

    def test_busy_prevents_navigation_and_cancel_restores_material_preview(self):
        self.tab.set_reference_image(self.image)
        self.tab.next_step_btn.click()
        self.tab.script_next_btn.click()
        self.tab._start_generation("Rendering")
        self.assertFalse(self.tab.workflow_stack.isEnabled())
        self.assertFalse(self.tab.stop_btn.isHidden())
        self.assertEqual(self.tab.preview_stack.currentWidget(), self.tab.preview)
        self.tab._go_to_step(0)
        self.assertEqual(self.tab.workflow_stack.currentIndex(), 2)
        self.tab._on_generate_cancelled()
        self.assertTrue(self.tab.workflow_stack.isEnabled())
        self.assertTrue(self.tab.stop_btn.isHidden())
        self.assertEqual(self.tab.preview_stack.currentWidget(), self.tab.asset_preview)

    def test_removing_material_clears_preview_and_disables_next(self):
        self.tab.set_reference_image(self.image)
        self.assertFalse(self.tab.asset_preview._original.isNull())
        self.tab._on_clear_reference_image()
        self.assertTrue(self.tab.asset_preview._original.isNull())
        self.assertFalse(self.tab.next_step_btn.isEnabled())

    def test_preview_selection_and_failed_render_keep_materials(self):
        self.tab.set_reference_image(self.image)
        other = self.folder / "reference.png"
        pixmap = QPixmap(60, 80)
        pixmap.fill()
        pixmap.save(str(other))
        self.tab._material_image_paths.append(other)
        self.tab._refresh_materials_strip()
        self.tab.preview_asset_selector.setCurrentIndex(1)
        self.assertEqual(self.tab._selected_asset_path, other)
        self.tab.next_step_btn.click()
        self.tab.script_next_btn.click()
        self.tab._start_generation("Rendering")
        self.tab._on_error("Render failed")
        self.assertEqual(self.tab.workflow_stack.currentIndex(), 2)
        self.assertEqual(self.tab.preview_stack.currentWidget(), self.tab.asset_preview)
        self.assertEqual(self.tab._reference_image_path, self.image)
        self.assertEqual(self.tab._material_image_paths, [other])
        self.assertTrue(self.tab.generate_btn.isEnabled())

    def test_sample_upload_is_sent_to_edit_and_output_becomes_material(self):
        with patch("app.ui.video_tab.QFileDialog.getOpenFileName", return_value=(str(self.image), "")):
            self.tab.attach_sample_btn.click()
        self.assertEqual(self.tab._asset_sample_path, self.image)
        self.assertIsNone(self.tab._reference_image_path)
        self.assertFalse(self.tab.next_step_btn.isEnabled())
        source = self.image.read_bytes()
        uploaded = []

        def edit(**kwargs):
            stream = kwargs["image"][1]
            uploaded.append(stream)
            self.assertEqual(stream.read(), source)
            self.assertIn("Warm morning light", kwargs["prompt"])
            return SimpleNamespace(usage=None, data=[SimpleNamespace(b64_json=base64.b64encode(source).decode())])

        with patch("app.core.image_client.OpenAI") as api:
            api.return_value.images.edit.side_effect = edit
            self.tab.generate_asset_btn.click()
            self.wait_worker()
            api.return_value.images.edit.assert_called_once()
            api.return_value.images.generate.assert_not_called()
        self.assertTrue(uploaded[0].closed)
        self.assertNotEqual(self.tab._reference_image_path, self.image)
        self.assertEqual(self.tab._reference_image_path.read_bytes(), source)
        self.assertEqual(self.image.read_bytes(), source)
        self.tab.clear_sample_btn.click()
        self.assertIsNone(self.tab._asset_sample_path)
        self.assertIsNotNone(self.tab._reference_image_path)

    def test_invalid_sample_does_not_replace_selection_or_call_api(self):
        with patch("app.ui.video_tab.QFileDialog.getOpenFileName", return_value=(str(self.image), "")):
            self.tab.attach_sample_btn.click()
        broken = self.folder / "broken.png"
        broken.write_text("not an image")
        with patch("app.ui.video_tab.QFileDialog.getOpenFileName", return_value=(str(broken), "")):
            self.tab.attach_sample_btn.click()
        self.assertEqual(self.tab._asset_sample_path, self.image)
        self.image.unlink()
        with patch("app.core.image_client.OpenAI") as api:
            self.tab.generate_asset_btn.click()
            api.assert_not_called()

    def test_face_reference_alone_and_with_scene_sample(self):
        face = self.folder / "portrait.png"
        face.write_bytes(self.image.read_bytes())
        with patch("app.ui.video_tab.QFileDialog.getOpenFileName", return_value=(str(face), "")):
            self.tab.attach_face_btn.click()
        self.assertEqual(self.tab._asset_face_path, face)
        self.assertIsNone(self.tab._reference_image_path)
        for use_sample in (False, True):
            with self.subTest(use_sample=use_sample):
                if use_sample:
                    with patch("app.ui.video_tab.QFileDialog.getOpenFileName", return_value=(str(self.image), "")):
                        self.tab.attach_sample_btn.click()
                streams = []

                def edit(**kwargs):
                    images = kwargs["image"] if isinstance(kwargs["image"], list) else [kwargs["image"]]
                    self.assertTrue(all(f[2] == "image/png" for f in images))
                    images = [f[1] for f in images]
                    streams.extend(images)
                    self.assertEqual([Path(f.name) for f in images], [face, self.image] if use_sample else [face])
                    self.assertTrue(all(f.read() == face.read_bytes() for f in images))
                    self.assertIn("Ảnh 1 là khuôn mặt", kwargs["prompt"])
                    if use_sample:
                        self.assertIn("Ảnh 2 là hình mẫu", kwargs["prompt"])
                    return SimpleNamespace(usage=None, data=[SimpleNamespace(
                        b64_json=base64.b64encode(face.read_bytes()).decode())])

                with patch("app.core.image_client.OpenAI") as api:
                    api.return_value.images.edit.side_effect = edit
                    self.tab.generate_asset_btn.click()
                    self.wait_worker()
                    api.return_value.images.edit.assert_called_once()
                    api.return_value.images.generate.assert_not_called()
                self.assertTrue(all(f.closed for f in streams))
        self.tab.clear_face_btn.click()
        self.assertIsNone(self.tab._asset_face_path)
        self.assertEqual(self.tab._asset_sample_path, self.image)
        self.assertIsNotNone(self.tab._reference_image_path)

    def test_missing_face_blocks_generation_and_failed_upload_closes_files(self):
        with patch("app.ui.video_tab.QFileDialog.getOpenFileName", return_value=(str(self.image), "")):
            self.tab.attach_face_btn.click()
        streams = []

        def fail_edit(**kwargs):
            streams.extend(f[1] for f in kwargs["image"])
            raise RuntimeError("Upload failed")

        with patch("app.core.image_client.OpenAI") as api:
            api.return_value.images.edit.side_effect = fail_edit
            with self.assertRaisesRegex(RuntimeError, "Upload failed"):
                ImageClient("fake").generate_image("Portrait", "1024x1024", self.folder,
                                                   reference_image_path=self.image, face_image_path=self.image)
        self.assertTrue(all(f.closed for f in streams))
        self.image.unlink()
        with patch("app.core.image_client.OpenAI") as api:
            self.tab.generate_asset_btn.click()
            api.assert_not_called()

    def test_inline_edit_chains_from_selected_version_and_keeps_original(self):
        self.tab.set_reference_image(self.image)
        self.tab._asset_face_path = self.image
        first = self.folder / "edit1.png"
        second = self.folder / "edit2.png"
        first.write_bytes(self.image.read_bytes())
        second.write_bytes(self.image.read_bytes())
        with patch("app.ui.video_tab.ImageClient") as client:
            client.return_value.generate_image.side_effect = [first, second]
            for source, instruction in ((self.image, "Change background"), (first, "Add flowers")):
                self.tab.asset_edit_input.setPlainText(instruction)
                self.tab.edit_asset_btn.click()
                self.assertFalse(self.tab.preview_asset_selector.isEnabled())
                self.assertFalse(self.tab.asset_version_combo.isEnabled())
                self.wait_worker()
                kwargs = client.return_value.generate_image.call_args.kwargs
                self.assertEqual(kwargs["reference_image_path"], source)
                self.assertEqual(kwargs["face_image_path"], self.image)
                self.assertIn(instruction, kwargs["prompt"])
        self.assertEqual(self.tab._reference_image_path, second)
        self.assertEqual(self.tab.asset_version_combo.count(), 3)
        self.tab.asset_version_combo.setCurrentIndex(0)
        self.assertEqual(self.tab._reference_image_path, self.image)
        self.tab.asset_version_combo.setCurrentIndex(1)
        self.assertEqual(self.tab._reference_image_path, first)
        self.assertTrue(self.image.is_file())
        self.assertTrue(second.is_file())

    def test_inline_reference_edit_replaces_only_selected_slot(self):
        self.tab.set_reference_image(self.image)
        refs = [self.folder / f"ref{i}.png" for i in range(4)]
        for path in refs:
            path.write_bytes(self.image.read_bytes())
        self.tab._material_image_paths = refs.copy()
        self.tab._refresh_materials_strip()
        self.tab.preview_asset_selector.setCurrentIndex(3)
        edited = self.folder / "edited-ref.png"
        edited.write_bytes(self.image.read_bytes())
        with patch("app.ui.video_tab.ImageClient") as client:
            client.return_value.generate_image.return_value = edited
            self.tab.asset_edit_input.setPlainText("Change outfit")
            self.tab.edit_asset_btn.click()
            self.wait_worker()
        self.assertEqual(self.tab._reference_image_path, self.image)
        self.assertEqual(self.tab._material_image_paths, [refs[0], refs[1], edited, refs[3]])
        self.tab.asset_version_combo.setCurrentIndex(0)
        self.assertEqual(self.tab._material_image_paths, refs)

    def test_inline_edit_failure_keeps_source_and_instruction(self):
        self.tab.set_reference_image(self.image)
        self.tab.asset_edit_input.setPlainText("Warm lighting")
        with patch("app.ui.video_tab.ImageClient") as client:
            client.return_value.generate_image.side_effect = RuntimeError("Edit failed")
            self.tab.edit_asset_btn.click()
            self.wait_worker()
        self.assertEqual(self.tab._reference_image_path, self.image)
        self.assertEqual(self.tab.asset_edit_input.toPlainText(), "Warm lighting")
        self.assertTrue(self.tab.edit_asset_btn.isEnabled())
        self.assertEqual(self.tab.asset_version_combo.count(), 1)

    def test_image_client_generation_fallback_and_unsupported_sample_model(self):
        with patch("app.core.image_client.OpenAI") as api:
            api.return_value.images.generate.return_value = SimpleNamespace(
                usage=None, data=[SimpleNamespace(b64_json=base64.b64encode(self.image.read_bytes()).decode())])
            client = ImageClient("fake")
            client.generate_image("A garden", "1024x1024", self.folder)
            api.return_value.images.generate.assert_called_once()
            api.return_value.images.edit.assert_not_called()
            with self.assertRaisesRegex(ValueError, "GPT Image"):
                ImageClient("fake", "dall-e-3").generate_image(
                    "A garden", "1024x1024", self.folder, reference_image_path=self.image)
            api.return_value.images.edit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
