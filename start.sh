#!/bin/bash
# CarlBox Server — startup script
# Creates a venv if needed, then launches the BLE + MIDI server.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "[SETUP] Creating virtual environment..."
    python3 -m venv --system-site-packages "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet bless mido
    echo "[SETUP] Done."
fi

exec "$VENV_DIR/bin/python3" "$SCRIPT_DIR/carlbox_server.py" "$@"
