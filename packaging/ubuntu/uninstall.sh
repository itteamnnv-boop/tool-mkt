#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${CLAUDE_STUDIO_PYTHON:-python3}" "$SCRIPT_DIR/ubuntu_setup.py" uninstall
