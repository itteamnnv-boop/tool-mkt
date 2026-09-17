#!/usr/bin/env bash
set -euo pipefail
INSTALL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$INSTALL_DIR/venv/bin/python"
if [[ ! -x "$PYTHON" || ! -f "$INSTALL_DIR/runtime/run.py" ]]; then
    printf '%s\n' 'Installation is incomplete. Run install.sh again.' >&2
    exit 1
fi
export CLAUDE_STUDIO_NO_RELOAD=1
export PYTHONUTF8=1
if [[ "${1:-}" == "--diagnose" ]]; then
    exec "$PYTHON" "$INSTALL_DIR/ubuntu_setup.py" diagnose
fi
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    printf '%s\n' 'A graphical Ubuntu desktop session is required.' >&2
    exit 1
fi
# Keep OAuth callbacks and desktop/keyring access in the existing login session.
cd -- "$INSTALL_DIR/runtime"
exec "$PYTHON" run.py "$@"
