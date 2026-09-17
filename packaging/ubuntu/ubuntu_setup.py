"""Ubuntu installation helpers; standard library only except optional diagnostics."""
from __future__ import annotations

import os
import platform
import shlex
import shutil
import sys
from pathlib import Path

APP_ID = "claude-content-studio"


def data_home() -> Path:
    value = os.environ.get("XDG_DATA_HOME", "")
    if value and not Path(value).is_absolute():
        raise SystemExit("XDG_DATA_HOME must be an absolute path.")
    return Path(value) if value else Path.home() / ".local" / "share"


def install_dir() -> Path:
    return data_home() / APP_ID


def check_platform() -> None:
    if sys.platform != "linux":
        raise SystemExit("This package requires Ubuntu Linux.")
    if not (3, 10) <= sys.version_info[:2] < (3, 15):
        raise SystemExit("Python 3.10 through 3.14 is required.")
    arch = platform.machine()
    required = {"x86_64": (2, 34), "aarch64": (2, 39)}.get(arch)
    if required is None:
        raise SystemExit("A 64-bit x86_64 or aarch64 system is required.")
    libc, version = platform.libc_ver()
    if libc != "glibc" or tuple(int(part) for part in version.split(".")[:2]) < required:
        raise SystemExit(f"glibc {'.'.join(map(str, required))}+ is required for {arch}.")


def write_text(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(0o755 if executable else 0o644)


def desktop_quote(value: str) -> str:
    # Desktop entry values are unescaped once before Exec is tokenized.
    value = value.replace("\\", "\\\\\\\\")
    for character in ('"', '`', '$'):
        value = value.replace(character, "\\\\" + character)
    return '"' + value.replace("%", "%%") + '"'


def install(source: Path, scripts: Path) -> None:
    target = install_dir()
    runtime = target / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / "app", runtime / "app", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(source / "run.py", runtime / "run.py")
    for name in ("launch.sh", "uninstall.sh", "ubuntu_setup.py"):
        write_text(target / name, (scripts / name).read_text(encoding="utf-8"), name.endswith(".sh"))
    launcher = Path.home() / ".local" / "bin" / APP_ID
    write_text(launcher, "#!/usr/bin/env bash\nexec " + shlex.quote(str(target / "launch.sh")) + ' "$@"\n', True)
    icon = data_home() / "icons" / "hicolor" / "scalable" / "apps" / (APP_ID + ".svg")
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "app" / "resources" / "studio.svg", icon)
    desktop = data_home() / "applications" / (APP_ID + ".desktop")
    write_text(desktop, "\n".join([
        "[Desktop Entry]", "Version=1.0", "Type=Application", "Name=Claude Content Studio",
        "Comment=Create content, images and videos; publish to social platforms",
        "Exec=" + desktop_quote(str(launcher)), "Icon=" + str(icon).replace("\\", "\\\\"),
        "Terminal=false", "Categories=Office;Graphics;", "StartupNotify=true",
        "StartupWMClass=claude-content-studio", "",
    ]))


def uninstall() -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise SystemExit("Run uninstall.sh as your desktop user, without sudo.")
    target = install_dir()
    resolved_base = data_home().resolve()
    # Never recurse through an install-directory symlink or delete the data root.
    if target.is_symlink() or target.resolve().parent != resolved_base or target.name != APP_ID:
        raise SystemExit("Refusing to remove an unexpected installation path.")
    for path in (
        Path.home() / ".local" / "bin" / APP_ID,
        data_home() / "applications" / (APP_ID + ".desktop"),
        data_home() / "icons" / "hicolor" / "scalable" / "apps" / (APP_ID + ".svg"),
    ):
        path.unlink(missing_ok=True)
    if target.exists():
        shutil.rmtree(target)
    print("Uninstalled. Settings, history, generated media and keyring credentials were preserved.")


def diagnose() -> None:
    print("Python:", sys.version.split()[0])
    print("System:", platform.platform())
    print("Installation:", install_dir())
    print("Desktop:", os.environ.get("XDG_SESSION_TYPE", "unknown"))
    try:
        import PySide6
        import keyring
        print("PySide6:", PySide6.__version__)
        backend = keyring.get_keyring()
        print("Keyring:", type(backend).__module__ + "." + type(backend).__name__)
        if backend.priority <= 0:
            raise RuntimeError("No usable system keyring backend found")
    except Exception as exc:
        print("Dependency/keyring error:", exc)
        print("Log into Ubuntu Desktop and unlock the login keyring using Passwords and Keys (seahorse).")
        raise SystemExit(1) from exc


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "path":
        print(install_dir())
    elif command == "check":
        check_platform()
    elif command == "install" and len(sys.argv) == 4:
        install(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
    elif command == "uninstall":
        uninstall()
    elif command == "diagnose":
        diagnose()
    else:
        raise SystemExit("Usage: ubuntu_setup.py check|path|install SOURCE SCRIPTS|uninstall|diagnose")


if __name__ == "__main__":
    main()
