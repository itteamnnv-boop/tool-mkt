"""Offline checks for Linux paths, desktop file opening and the Ubuntu installer archive."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from app import config
from app.ui.gallery_tab import _GalleryCard
from app.ui.video_tab import VideoTab
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from types import SimpleNamespace


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup = load_module("ubuntu_setup", ROOT / "packaging" / "ubuntu" / "ubuntu_setup.py")
builder = load_module("package_ubuntu", ROOT / "tools" / "package_ubuntu.py")


class UbuntuChecks(unittest.TestCase):
    def test_xdg_and_generated_media(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            xdg = Path(temp) / "xdg"
            with patch.object(Path, "home", return_value=home), patch.object(config.sys, "platform", "linux"), patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg)}, clear=True):
                self.assertEqual(config.app_data_dir(), xdg / config.APP_NAME)
                config.save_settings({"glass_style": "crystal"})
                self.assertEqual(config.load_settings()["glass_style"], "crystal")
                self.assertEqual(config.output_dir("videos"), xdg / config.APP_NAME / "output" / "videos")
            with patch.object(Path, "home", return_value=home), patch.object(config.sys, "platform", "linux"), patch.dict(os.environ, {"XDG_DATA_HOME": "relative/path"}, clear=True):
                self.assertEqual(config.app_data_dir(), home / ".local" / "share" / config.APP_NAME)

    def test_legacy_linux_history_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            legacy = home / config.APP_NAME
            legacy.mkdir()
            (legacy / "history.sqlite3").write_bytes(b"existing history")
            with patch.object(Path, "home", return_value=home), patch.object(config.sys, "platform", "linux"), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(config.app_data_dir(), legacy)
                self.assertEqual((legacy / "history.sqlite3").read_bytes(), b"existing history")

    def test_windows_paths_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(config.sys, "platform", "win32"), patch.dict(os.environ, {"APPDATA": temp}):
                self.assertEqual(config.app_data_dir(), Path(temp) / config.APP_NAME)

    def test_local_media_uri_and_failure(self):
        for method, attribute in ((_GalleryCard._on_open, "file_path"), (VideoTab._on_open_video, "_current_video_path")):
            from unittest.mock import Mock
            media = ROOT / "example image #1.mp4"
            widget = SimpleNamespace(**{attribute: media}, log_message=SimpleNamespace(emit=Mock()))
            with patch.object(QDesktopServices, "openUrl", return_value=True) as opener:
                method(widget)
                url = opener.call_args.args[0]
                self.assertIsInstance(url, QUrl)
                self.assertTrue(url.isLocalFile())
                self.assertEqual(Path(url.toLocalFile()), media.resolve())
                widget.log_message.emit.assert_not_called()
            with patch.object(QDesktopServices, "openUrl", return_value=False):
                method(widget)
                self.assertEqual(widget.log_message.emit.call_args.args[1], "error")

    def test_install_update_and_uninstall_preserve_data(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home with spaces"
            with patch.object(Path, "home", return_value=home), patch.dict(os.environ, {}, clear=True):
                data = setup.data_home() / config.APP_NAME
                data.mkdir(parents=True)
                (data / "history.sqlite3").write_bytes(b"preserve")
                setup.install(ROOT, ROOT / "packaging" / "ubuntu")
                target = setup.install_dir()
                self.assertTrue((target / "runtime" / "app" / "resources" / "crystal.qss").exists())
                desktop = (setup.data_home() / "applications" / "claude-content-studio.desktop").read_text(encoding="utf-8")
                self.assertIn('Exec="', desktop)
                launcher = home / ".local" / "bin" / "claude-content-studio"
                self.assertIn('"$@"', launcher.read_text())
                (target / "venv").mkdir()
                (target / "venv" / "marker").write_text("keep venv on update")
                setup.install(ROOT, ROOT / "packaging" / "ubuntu")
                self.assertTrue((target / "venv" / "marker").exists())
                with patch.object(setup.os, "geteuid", return_value=1000, create=True):
                    setup.uninstall()
                self.assertFalse(target.exists())
                self.assertFalse(launcher.exists())
                self.assertEqual((data / "history.sqlite3").read_bytes(), b"preserve")

    def test_glibc_architecture_requirements(self):
        with patch.object(setup.sys, "platform", "linux"), patch.object(setup.platform, "machine", return_value="aarch64"), patch.object(setup.platform, "libc_ver", return_value=("glibc", "2.35")):
            with self.assertRaises(SystemExit):
                setup.check_platform()
        with patch.object(setup.sys, "platform", "linux"), patch.object(setup.platform, "machine", return_value="x86_64"), patch.object(setup.platform, "libc_ver", return_value=("glibc", "2.35")):
            setup.check_platform()

    def test_uninstall_rejects_symlink_target(self):
        with patch.object(setup.os, "geteuid", return_value=1000, create=True), patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(SystemExit):
                setup.uninstall()

    def test_archive_content_permissions_and_checksums(self):
        archive = ROOT / "dist" / (builder.PACKAGE + ".tar.gz")
        checksum = archive.with_name(archive.name + ".sha256").read_text().split()[0]
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), checksum)
        with tarfile.open(archive, "r:gz") as tar:
            contents = {}
            for member in tar.getmembers():
                relative = member.name.removeprefix(builder.PACKAGE + "/")
                self.assertFalse(member.name.startswith("/"))
                self.assertNotIn("..", Path(relative).parts)
                self.assertNotIn(Path(relative).parts[0], {"output", ".venv", ".git", ".env"})
                self.assertNotIn(Path(relative).name, {"config.json", "history.sqlite3"})
                contents[relative] = tar.extractfile(member).read()
                self.assertNotIn(b"\r\n", contents[relative])
                if relative.endswith(".sh"):
                    self.assertEqual(member.mode, 0o755)
                if relative.endswith(".py"):
                    compile(contents[relative], relative, "exec")
            for line in contents["SHA256SUMS"].decode("ascii").splitlines():
                expected, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256(contents[name]).hexdigest(), expected)
            self.assertIn("app/resources/crystal.qss", contents)
            self.assertIn("app/resources/studio.svg", contents)


if __name__ == "__main__":
    unittest.main(verbosity=2)
