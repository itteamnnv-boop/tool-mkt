"""Build a source installer tarball for Ubuntu without copying local data/secrets.

Run with Python on Windows or Linux: python tools/package_ubuntu.py
"""
from __future__ import annotations

import gzip
import hashlib
import io
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
PACKAGE = f"claude-content-studio-ubuntu-{VERSION}"


def payloads(root: Path) -> dict[str, bytes]:
    selected = {"run.py": root / "run.py", "README.md": root / "README.md"}
    for path in sorted((root / "app").rglob("*")):
        if path.is_file() and path.suffix in {".py", ".qss", ".svg"} and "__pycache__" not in path.parts:
            selected[path.relative_to(root).as_posix()] = path
    for name in ("install.sh", "launch.sh", "uninstall.sh", "ubuntu_setup.py", "requirements.txt", "README-UBUNTU.md"):
        selected[name] = root / "packaging" / "ubuntu" / name
    selected["tools/ui_smoke.py"] = root / "tools" / "ui_smoke.py"
    contents = {name: path.read_bytes().replace(b"\r\n", b"\n") for name, path in selected.items()}
    sums = "".join(f"{hashlib.sha256(content).hexdigest()}  {name}\n" for name, content in sorted(contents.items()))
    contents["SHA256SUMS"] = sums.encode("ascii")
    return contents


def build(output: Path, root: Path = ROOT) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (PACKAGE + ".tar.gz")
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for name, content in sorted(payloads(root).items()):
                    info = tarfile.TarInfo(f"{PACKAGE}/{name}")
                    info.size = len(content)
                    info.mode = 0o755 if name.endswith(".sh") else 0o644
                    info.mtime = 0
                    tar.addfile(info, io.BytesIO(content))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Created: {archive} ({archive.stat().st_size:,} bytes)")
    print(f"SHA256: {digest}")
    return archive


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("Usage: python tools/package_ubuntu.py")
    build(ROOT / "dist")
