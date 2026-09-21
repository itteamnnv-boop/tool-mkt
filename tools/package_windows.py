"""Build a Windows installer package: PyInstaller bundle (standalone .exe, no Python needed
on the target machine) + a PowerShell installer (Start Menu/Desktop shortcut, per-user
"Add or Remove Programs" entry, and a matching uninstaller) — zipped together.

Must run on Windows (PyInstaller does not cross-compile): python tools/package_windows.py
Requires pyinstaller in the current environment: pip install pyinstaller
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
APP_NAME = "ClaudeContentStudio"


def build_pyinstaller_bundle(root: Path = ROOT) -> Path:
    """Runs PyInstaller and returns the resulting dist/ClaudeContentStudio bundle dir.
    Shared by package_windows.py (zip + PowerShell installer) and package_windows_installer.py
    (Inno Setup wizard) so both ship the exact same build."""
    if sys.platform != "win32":
        raise SystemExit("This must run on Windows — PyInstaller bundles the platform it runs on.")

    build_dir = root / "build"
    bundle_dir = root / "dist" / APP_NAME
    spec_file = root / f"{APP_NAME}.spec"
    for stale in (build_dir, bundle_dir, spec_file):
        if stale.exists():
            shutil.rmtree(stale) if stale.is_dir() else stale.unlink()

    print("Running PyInstaller (this takes a minute)...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--windowed",
            "--collect-all",
            "imageio_ffmpeg",
            "--name",
            APP_NAME,
            "--add-data",
            f"{root / 'app' / 'resources'};app/resources",
            str(root / "run.py"),
        ],
        cwd=root,
        check=True,
    )
    return bundle_dir


def build(output: Path, root: Path = ROOT) -> Path:
    bundle_dir = build_pyinstaller_bundle(root)

    windows_pkg_dir = root / "packaging" / "windows"
    shutil.copy2(windows_pkg_dir / "install.ps1", bundle_dir / "install.ps1")
    shutil.copy2(windows_pkg_dir / "uninstall.ps1", bundle_dir / "uninstall.ps1")

    output.mkdir(parents=True, exist_ok=True)
    zip_path = output / f"claude-content-studio-windows-{VERSION}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(bundle_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(bundle_dir.parent))

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    zip_path.with_name(zip_path.name + ".sha256").write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")
    print(f"Created: {zip_path} ({zip_path.stat().st_size:,} bytes)")
    print(f"SHA256: {digest}")
    return zip_path


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("Usage: python tools/package_windows.py")
    build(ROOT / "dist")
