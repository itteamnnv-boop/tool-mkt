"""Build a real Debian .deb package for Ubuntu — no dpkg-deb/ar/fakeroot required, so this
runs on Windows too. Reuses the same file selection as package_ubuntu.py (the source
installer) so both packages ship identical app content; this one just wraps it as a proper
.deb (system libs declared as apt Depends, postinst builds the private venv on install).

Caveat: only the archive format is built here — nothing is compiled, and nothing is actually
installed or run. This has NOT been tested with a real `apt install`/`dpkg -i` on Ubuntu
(no Linux/WSL available in the environment that built it); verify on a real Ubuntu box before
distributing it.

Run with Python on Windows or Linux: python tools/package_deb.py
"""
from __future__ import annotations

import gzip
import hashlib
import io
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_ubuntu import payloads  # noqa: E402 - path tweak above must run first

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
PACKAGE_NAME = "claude-content-studio"
ARCH = "all"
INSTALL_DIR = f"/opt/{PACKAGE_NAME}"

# Same apt packages install.sh installs manually — declaring them as Depends lets apt/dpkg
# pull them in automatically on `apt install ./claude-content-studio_*.deb`.
DEPENDS = (
    "python3 (>= 3.10), python3-venv, python3-pip, gnome-keyring, dbus-user-session, "
    "xdg-utils, fonts-dejavu-core, libgl1, libegl1, libopengl0, libfontconfig1, "
    "libx11-xcb1, libxkbcommon-x11-0, libxcb1, libxcb-cursor0, libxcb-icccm4, "
    "libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, "
    "libxcb-xfixes0, libxcb-xinerama0, libxcb-xkb1, libxcb-sync1, libxcb-render0, "
    "libxcb-shm0, libsm6, libice6, libxrender1"
)

CONTROL_TEMPLATE = f"""Package: {PACKAGE_NAME}
Version: {VERSION}
Section: utils
Priority: optional
Architecture: {ARCH}
Depends: {DEPENDS}
Installed-Size: {{installed_size_kb}}
Maintainer: Claude Content Studio Packager <packager@localhost>
Description: AI content studio for writing posts, generating images/video, and publishing
 Desktop app (Python + PySide6) that writes Facebook-style posts with Claude/OpenAI,
 generates images and avatar/AI videos, then publishes to Facebook, TikTok, and YouTube.
 Installs a private virtualenv under {INSTALL_DIR} on first setup; does not touch the
 system Python. Not affiliated with or endorsed by Anthropic, TikTok, or Google.
"""

POSTINST = f"""#!/bin/sh
set -e
APP_DIR="{INSTALL_DIR}"

if [ ! -x "$APP_DIR/venv/bin/python" ]; then
    python3 -m venv "$APP_DIR/venv"
    "$APP_DIR/venv/bin/python" -m pip install --upgrade pip
    "$APP_DIR/venv/bin/python" -m pip install --only-binary=:all: -r "$APP_DIR/requirements.txt"
fi
"$APP_DIR/venv/bin/python" -m pip check

chmod -R a+rX "$APP_DIR"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi

exit 0
"""

POSTRM = f"""#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -rf "{INSTALL_DIR}"
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi
exit 0
"""

LAUNCHER = f"""#!/bin/sh
exec "{INSTALL_DIR}/venv/bin/python" "{INSTALL_DIR}/run.py" "$@"
"""

DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=Claude Content Studio
Comment=AI content, image, and video studio for Facebook/TikTok/YouTube
Exec=/usr/bin/claude-content-studio
Terminal=false
Categories=Office;Network;
"""

COPYRIGHT = f"""Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: {PACKAGE_NAME}

Files: *
Copyright: The app's owner
License: Proprietary
 For personal/internal use. Not redistributed under an open-source license.
"""


def _clean(content: bytes) -> bytes:
    return content.replace(b"\r\n", b"\n")


def _dir_ancestors(paths: list[str]) -> list[str]:
    """All parent directories implied by `paths`, deepest-last so dpkg creates them
    outside-in (dpkg's unpacker does not auto-vivify missing parent directories the way
    a plain `tar -x` would, so every level needs its own explicit archive entry)."""
    dirs: set[str] = set()
    for path in paths:
        parts = path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    return sorted(dirs, key=lambda d: d.count("/"))


def _tar_gz(members: dict[str, tuple[bytes, int]]) -> bytes:
    """members: {archive_path: (content, unix_mode)}. Deterministic (mtime=0), GNU tar
    format for the widest dpkg compatibility."""
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
            for dirpath in _dir_ancestors(list(members.keys())):
                info = tarfile.TarInfo(dirpath)
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                tar.addfile(info)
            for path, (content, mode) in sorted(members.items()):
                info = tarfile.TarInfo(path)
                info.size = len(content)
                info.mode = mode
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _ar_member(name: str, content: bytes) -> bytes:
    if len(name) > 16:
        raise ValueError(f"ar member name too long for classic header: {name}")
    header = (
        name.ljust(16).encode("ascii")
        + b"0".ljust(12)  # mtime
        + b"0".ljust(6)  # uid
        + b"0".ljust(6)  # gid
        + b"100644".ljust(8)  # mode (octal)
        + str(len(content)).ljust(10).encode("ascii")
        + b"`\n"
    )
    body = content + (b"\n" if len(content) % 2 else b"")
    return header + body


def build_deb(output: Path, root: Path = ROOT) -> Path:
    src = payloads(root)  # {relative_path: content} — same files package_ubuntu.py ships

    data_members: dict[str, tuple[bytes, int]] = {}
    for name, content in src.items():
        mode = 0o755 if name.endswith(".sh") or name.endswith(".py") else 0o644
        data_members[f"{INSTALL_DIR.lstrip('/')}/{name}"] = (_clean(content), mode)
    data_members["usr/bin/claude-content-studio"] = (_clean(LAUNCHER.encode()), 0o755)
    data_members["usr/share/applications/claude-content-studio.desktop"] = (
        _clean(DESKTOP_ENTRY.encode()),
        0o644,
    )
    data_members[f"usr/share/doc/{PACKAGE_NAME}/copyright"] = (_clean(COPYRIGHT.encode()), 0o644)
    data_tar_gz = _tar_gz(data_members)

    installed_size_kb = max(1, sum(len(c) for c, _ in data_members.values()) // 1024)
    control_members = {
        "control": (_clean(CONTROL_TEMPLATE.format(installed_size_kb=installed_size_kb).encode()), 0o644),
        "postinst": (_clean(POSTINST.encode()), 0o755),
        "postrm": (_clean(POSTRM.encode()), 0o755),
    }
    control_tar_gz = _tar_gz(control_members)

    ar_bytes = (
        b"!<arch>\n"
        + _ar_member("debian-binary", b"2.0\n")
        + _ar_member("control.tar.gz", control_tar_gz)
        + _ar_member("data.tar.gz", data_tar_gz)
    )

    output.mkdir(parents=True, exist_ok=True)
    deb_path = output / f"{PACKAGE_NAME}_{VERSION}_{ARCH}.deb"
    deb_path.write_bytes(ar_bytes)
    digest = hashlib.sha256(ar_bytes).hexdigest()
    deb_path.with_name(deb_path.name + ".sha256").write_text(f"{digest}  {deb_path.name}\n", encoding="ascii")
    print(f"Created: {deb_path} ({deb_path.stat().st_size:,} bytes)")
    print(f"SHA256: {digest}")
    print(f"Built at: {time.strftime('%Y-%m-%d %H:%M:%S')} (from Windows — NOT verified with a real dpkg/apt yet)")
    return deb_path


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("Usage: python tools/package_deb.py")
    build_deb(ROOT / "dist")
