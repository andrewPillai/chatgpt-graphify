#!/bin/bash
set -e

SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_DIR="$HOME/Library/Application Support/ChatGPT Graphify"
VENV_DIR="$INSTALL_DIR/venv"
APP_DIR="$HOME/Applications/ChatGPT Graphify.app"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.9 or newer is required. Install it from https://www.python.org/downloads/macos/ and run this installer again."
  read -r -p "Press Return to close..."
  exit 1
fi

mkdir -p "$INSTALL_DIR"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install "$SOURCE_DIR"

mkdir -p "$APP_DIR/Contents/MacOS"
cp "$SOURCE_DIR/installers/macos/Info.plist" "$APP_DIR/Contents/Info.plist"
cp "$SOURCE_DIR/installers/macos/ChatGPT Graphify" "$APP_DIR/Contents/MacOS/ChatGPT Graphify"
chmod +x "$APP_DIR/Contents/MacOS/ChatGPT Graphify"
open "$APP_DIR"
