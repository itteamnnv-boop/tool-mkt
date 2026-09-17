"""Build a real Windows Setup.exe wizard (Inno Setup) — installer UI with Next/Next/Finish,
Start Menu + optional Desktop shortcut, and a proper "Add or Remove Programs" entry, all
handled natively by Inno Setup (no hand-rolled PowerShell/registry code needed).

Requires Inno Setup 6 (ISCC.exe) — install with:
  winget install --id JRSoftware.InnoSetup
Must run on Windows (PyInstaller does not cross-compile): python tools/package_windows_installer.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_windows import ROOT, build_pyinstaller_bundle  # noqa: E402 - path tweak above must run first

ISCC_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path.home() / r"AppData\Local\Programs\Inno Setup 6\ISCC.exe",
]


def find_iscc() -> Path:
    for candidate in ISCC_CANDIDATES:
        if candidate.exists():
            return candidate
    raise SystemExit(
        "Inno Setup (ISCC.exe) not found. Install it first:\n"
        "  winget install --id JRSoftware.InnoSetup\n"
        "then re-run this script."
    )


def build(root: Path = ROOT) -> Path:
    if sys.platform != "win32":
        raise SystemExit("This must run on Windows.")
    iscc = find_iscc()
    build_pyinstaller_bundle(root)

    script = root / "packaging" / "windows" / "setup.iss"
    print(f"Compiling installer with {iscc} ...")
    subprocess.run([str(iscc), str(script)], check=True)

    output = root / "dist" / "ClaudeContentStudioSetup.exe"
    if not output.exists():
        raise SystemExit(f"Inno Setup reported success but {output} is missing — check its OutputDir/OutputBaseFilename.")
    print(f"Created: {output} ({output.stat().st_size:,} bytes)")
    return output


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("Usage: python tools/package_windows_installer.py")
    build()
