"""Offline reference-video tests: real audio conversion, mocked AI, real Qt signals."""
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
if sys.platform == 'win32':
    os.environ['QT_QPA_FONTDIR'] = 'C:/Windows/Fonts'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import imageio_ffmpeg
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import config
from app.core.content_prompts import build_video_script_from_reference_user_prompt
from app.core.transcription_client import TranscriptionClient
from app.ui.video_tab import VideoTab, PROVIDER_GROK


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def ffmpeg(self, *args):
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-v', 'error', *args],
                       check=True, capture_output=True, timeout=60,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def test_large_source_is_compacted_and_cleaned(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'large.wav'
            self.ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=440:duration=80',
                        '-ar', '96000', '-ac', '2', str(source))
            self.assertGreater(source.stat().st_size, 25 * 1024 * 1024)
            uploads = []

            def transcribe(**kwargs):
                stream = kwargs['file']
                uploads.append(Path(stream.name))
                self.assertLess(Path(stream.name).stat().st_size, 25 * 1024 * 1024)
                return SimpleNamespace(text='Reference transcript')

            with patch('app.core.transcription_client.OpenAI') as api:
                api.return_value.audio.transcriptions.create.side_effect = transcribe
                result = TranscriptionClient('fake').transcribe(source)
            self.assertEqual(result, 'Reference transcript')
            self.assertTrue(source.exists())
            self.assertTrue(uploads)
            self.assertFalse(uploads[0].exists())

    def test_segments_keep_order_and_video_without_audio_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'long.wav'
            self.ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=440:duration=601',
                        '-ar', '8000', str(source))
            with patch('app.core.transcription_client.OpenAI') as api:
                api.return_value.audio.transcriptions.create.side_effect = [
                    SimpleNamespace(text='First'), SimpleNamespace(text='Second')]
                client = TranscriptionClient('fake')
                self.assertEqual(client.transcribe(source), 'First\nSecond')
                silent = Path(folder) / 'silent.mp4'
                self.ffmpeg('-f', 'lavfi', '-i', 'color=black:s=32x32:d=1', '-an', str(silent))
                with self.assertRaisesRegex(RuntimeError, 'âm thanh'):
                    client.transcribe(silent)
                self.assertEqual(api.return_value.audio.transcriptions.create.call_count, 2)

    def wait(self, condition):
        for _ in range(250):
            QTest.qWait(10)
            if condition():
                return
        self.fail('Worker timed out')

    def test_select_then_analyze_fills_prompt_and_failure_keeps_it(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(config, 'load_settings', return_value=dict(config.DEFAULT_SETTINGS)), \
                patch.object(config, 'save_settings'), \
                patch.object(config, 'get_secret', return_value='fake'), \
                patch('app.ui.video_tab.TranscriptionClient') as transcriber, \
                patch('app.ui.video_tab.get_text_client') as writer:
            source = Path(folder) / 'reference.mp4'
            source.touch()
            tab = VideoTab()
            tab.provider_combo.setCurrentIndex(tab.provider_combo.findData(PROVIDER_GROK))
            tab.duration_spin.setValue(12)
            tab.aspect_combo.setCurrentText('9:16')
            tab.script_input.setPlainText('Existing prompt')
            with patch('app.ui.video_tab.QFileDialog.getOpenFileName', return_value=(str(source), '')):
                tab.reference_video_btn.click()
            transcriber.assert_not_called()
            self.assertEqual(tab.script_input.toPlainText(), 'Existing prompt')
            self.assertTrue(tab.analyze_reference_btn.isEnabled())
            gate = threading.Event()
            self.addCleanup(gate.set)
            transcriber.return_value.transcribe.side_effect = lambda path: (gate.wait(2), 'Reference words')[1]
            writer.return_value.suggest_video_script_from_reference.return_value = 'A cinematic garden scene'
            tab.analyze_reference_btn.click()
            self.assertFalse(tab.generate_btn.isEnabled())
            self.assertTrue(tab.script_input.isReadOnly())
            gate.set()
            self.wait(lambda: not tab._reference_busy and not tab._worker.isRunning())
            self.assertEqual(tab.script_input.toPlainText(), 'A cinematic garden scene')
            self.assertFalse(tab.script_input.isReadOnly())
            writer.return_value.suggest_video_script_from_reference.assert_called_once_with(
                'Reference words', '', target='grok', duration=12, aspect_ratio='9:16')
            self.assertTrue(tab.generate_btn.isEnabled())
            writer.return_value.suggest_video_script_from_reference.return_value = ''
            tab.analyze_reference_btn.click()
            self.wait(lambda: not tab._reference_busy and not tab._worker.isRunning())
            self.assertEqual(tab.script_input.toPlainText(), 'A cinematic garden scene')
            self.assertTrue(tab.analyze_reference_btn.isEnabled())
            source.unlink()
            tab.analyze_reference_btn.click()
            self.assertFalse(tab.analyze_reference_btn.isEnabled())
            tab.deleteLater()

    def test_provider_specific_prompt(self):
        grok = build_video_script_from_reference_user_prompt('Sample', 'Product', 'grok', 12, '9:16')
        self.assertIn('12 giây', grok)
        self.assertIn('9:16', grok)
        self.assertIn('máy quay', grok)
        heygen = build_video_script_from_reference_user_prompt('Sample', 'Product')
        self.assertIn('Chỉ trả về lời thoại', heygen)


if __name__ == '__main__':
    unittest.main()
