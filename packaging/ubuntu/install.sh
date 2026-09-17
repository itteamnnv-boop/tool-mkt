#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
    printf '%s\n' 'Usage: bash install.sh [--skip-system-deps]' \
        'Installs Claude Content Studio for your desktop user.' \
        'Default: installs Ubuntu libraries with sudo, then Python dependencies in a private venv.'
    exit 0
fi
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--skip-system-deps" ) ]]; then
    printf '%s\n' 'Unknown option. Use --help.' >&2
    exit 2
fi
if [[ "$(uname -s)" != "Linux" ]]; then
    printf '%s\n' 'This installer requires Ubuntu Linux.' >&2
    exit 1
fi
if [[ "$EUID" -eq 0 ]]; then
    printf '%s\n' 'Run bash install.sh as your desktop user, without sudo. Only apt uses sudo.' >&2
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR"
if [[ ! -d "$SOURCE_DIR/app" ]]; then
    SOURCE_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
fi
if [[ ! -f "$SOURCE_DIR/run.py" || ! -f "$SCRIPT_DIR/ubuntu_setup.py" ]]; then
    printf '%s\n' 'Incomplete package: run.py or ubuntu_setup.py is missing.' >&2
    exit 1
fi
if [[ -f "$SOURCE_DIR/SHA256SUMS" ]]; then
    (cd -- "$SOURCE_DIR" && sha256sum --check --quiet SHA256SUMS)
fi

if [[ "${1:-}" != "--skip-system-deps" ]]; then
    if ! command -v apt-get >/dev/null || ! command -v sudo >/dev/null; then
        printf '%s\n' 'Ubuntu apt-get and sudo are required. See README-UBUNTU.md.' >&2
        exit 1
    fi
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip \
        gnome-keyring dbus-user-session xdg-utils fonts-dejavu-core \
        libgl1 libegl1 libopengl0 libfontconfig1 libx11-xcb1 libxkbcommon-x11-0 \
        libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xfixes0 \
        libxcb-xinerama0 libxcb-xkb1 libxcb-sync1 libxcb-render0 libxcb-shm0 \
        libsm6 libice6 libxrender1
fi

PYTHON="${CLAUDE_STUDIO_PYTHON:-python3}"
"$PYTHON" "$SCRIPT_DIR/ubuntu_setup.py" check
INSTALL_DIR="$("$PYTHON" "$SCRIPT_DIR/ubuntu_setup.py" path)"
"$PYTHON" -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip
"$INSTALL_DIR/venv/bin/python" -m pip install --only-binary=:all: -r "$SCRIPT_DIR/requirements.txt"
"$INSTALL_DIR/venv/bin/python" -m pip check
"$INSTALL_DIR/venv/bin/python" "$SCRIPT_DIR/ubuntu_setup.py" install "$SOURCE_DIR" "$SCRIPT_DIR"
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "${XDG_DATA_HOME:-$HOME/.local/share}/applications" || true
fi
printf '\n%s\n' 'Installed. Open Claude Content Studio from Applications, or run:' \
    "$HOME/.local/bin/claude-content-studio"
