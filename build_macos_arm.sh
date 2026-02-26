#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${APP_NAME:-xmonitor-qt6}"
ENTRY_SCRIPT="${ENTRY_SCRIPT:-start_qt6.py}"
VENV_DIR="${VENV_DIR:-.venv-macos-arm64}"
DIST_DIR="${DIST_DIR:-dist}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Error: this script must run on macOS." >&2
  exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Error: this script is for macOS ARM64 (M1/M2/M3)." >&2
  echo "Current arch: $(uname -m)" >&2
  exit 1
fi

if [[ ! -f "$ENTRY_SCRIPT" ]]; then
  echo "Error: entry script not found: $ENTRY_SCRIPT" >&2
  exit 1
fi

echo "[1/6] Create venv: $VENV_DIR"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "[2/6] Upgrade pip toolchain"
python -m pip install --upgrade pip setuptools wheel

echo "[3/6] Install dependencies"
python -m pip install -r requirements_gui.txt
python -m pip install pyinstaller

echo "[4/6] Clean old build artifacts"
rm -rf build "$DIST_DIR"
rm -f ./*.spec

echo "[5/6] Build .app with PyInstaller"
pyinstaller "$ENTRY_SCRIPT" \
  --name "$APP_NAME" \
  --windowed \
  --onedir \
  --noconfirm \
  --clean \
  --collect-all PyQt6 \
  --collect-all PyQt6.QtWebEngineWidgets \
  --add-data "templates:templates"

APP_PATH="$DIST_DIR/$APP_NAME.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Error: build failed, app not found: $APP_PATH" >&2
  exit 1
fi

echo "[6/6] Pack tar.gz"
ARCHIVE="$DIST_DIR/x-monitor-pro-macos-arm64.tar.gz"
tar -czf "$ARCHIVE" -C "$DIST_DIR" "$APP_NAME.app"

echo
echo "Build complete:"
echo "- App: $APP_PATH"
echo "- Archive: $ARCHIVE"
echo
echo "If Gatekeeper blocks app on another Mac:"
echo "xattr -dr com.apple.quarantine \"$APP_PATH\""
