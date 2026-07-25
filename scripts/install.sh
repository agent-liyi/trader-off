#!/bin/bash
# trader-off install script — symlinks the unified `to` CLI to /usr/local/bin
# so it's available globally without `uv run` or activating venv.
# Usage: bash scripts/install.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="$REPO_DIR/.venv/bin"
TARGET_DIR="/usr/local/bin"

if [ ! -d "$VENV_BIN" ]; then
    echo "Virtual environment not found. Run 'uv sync' first."
    exit 1
fi

if [ ! -x "$VENV_BIN/to" ]; then
    echo "'to' entry point not found. Run 'uv sync' to regenerate it."
    exit 1
fi

if [ ! -w "$TARGET_DIR" ]; then
    echo "Need write permission to $TARGET_DIR — using sudo..."
    USE_SUDO=1
else
    USE_SUDO=0
fi

# Remove legacy trader-off-* symlinks that point into this repo's venv.
removed=0
for link in "$TARGET_DIR"/trader-off-*; do
    [ -L "$link" ] || continue
    case "$(readlink "$link")" in
        "$VENV_BIN"/*)
            if [ "$USE_SUDO" -eq 1 ]; then
                sudo rm -f "$link"
            else
                rm -f "$link"
            fi
            removed=$((removed + 1))
            ;;
    esac
done

if [ "$USE_SUDO" -eq 1 ]; then
    sudo ln -sf "$VENV_BIN/to" "$TARGET_DIR/to"
else
    ln -sf "$VENV_BIN/to" "$TARGET_DIR/to"
fi

echo "Linked 'to' to $TARGET_DIR (removed $removed legacy trader-off-* links)"
echo ""
echo "Try: to status"
