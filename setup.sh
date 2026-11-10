#!/usr/bin/env bash
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"
VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python 3 was not found. Install Python 3.10 or later, then run this script again." >&2
    exit 1
fi

if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Python 3.10 or later is required." >&2
    exit 1
fi

if [ -e "$VENV_DIR/Scripts/python.exe" ]; then
    echo "A Windows virtual environment exists at .venv. Use a separate Linux checkout or move the Windows environment before running setup." >&2
    exit 1
fi

if [ ! -x "$VENV_PYTHON" ]; then
    if ! "$PYTHON" -m venv "$VENV_DIR"; then
        echo "Failed to create the virtual environment. Install your distribution's venv package and try again." >&2
        exit 1
    fi
fi

if ! "$VENV_PYTHON" -m pip install --upgrade pip; then
    echo "Failed to upgrade pip." >&2
    exit 1
fi

if ! "$VENV_PYTHON" -m pip install -e .; then
    echo "Failed to install pyTaskFlow." >&2
    exit 1
fi

echo
echo "Setup complete. Run ./pyTaskFlow.sh to start pyTaskFlow."
