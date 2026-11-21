#!/usr/bin/env bash
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "Python virtual environment was not found. Run ./setup.sh first." >&2
    exit 1
fi

exec "$PYTHON" -m pytaskflow "$@"
