#!/bin/bash
# trader-off install script — symlinks all CLI binaries to /usr/local/bin
# so they're available globally without `uv run` or activating venv.
# Usage: bash scripts/install.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="$REPO_DIR/.venv/bin"
TARGET_DIR="/usr/local/bin"

if [ ! -d "$VENV_BIN" ]; then
    echo "Virtual environment not found. Run 'uv sync' first."
    exit 1
fi

if [ ! -w "$TARGET_DIR" ]; then
    echo "Need write permission to $TARGET_DIR — using sudo..."
    USE_SUDO=1
else
    USE_SUDO=0
fi

count=0
for bin in "$VENV_BIN"/trader-off-*; do
    name=$(basename "$bin")
    target="$TARGET_DIR/$name"
    if [ "$USE_SUDO" -eq 1 ]; then
        sudo ln -sf "$bin" "$target"
    else
        ln -sf "$bin" "$target"
    fi
    count=$((count + 1))
done

echo "Linked $count trader-off commands to $TARGET_DIR"
echo ""
echo "Try: trader-off-status"
