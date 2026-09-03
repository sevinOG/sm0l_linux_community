#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required on PATH."
  exit 1
fi
if ! python3 -c "import venv, ensurepip" >/dev/null 2>&1; then
  echo "Python venv is required (ensurepip missing)."
  echo "Debian/Ubuntu: sudo apt install python3-venv python3-pip"
  echo "Fedora:        sudo dnf install python3-virtualenv"
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating venv..."
  python3 -m venv .venv
fi

echo "Installing deps..."
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install pyinstaller

echo "Generating icon..."
.venv/bin/python scripts/make_icon.py

echo "Compiling..."
.venv/bin/python -m compileall -q src sm0l.py

echo "Building binary..."
.venv/bin/python -m PyInstaller build.spec --noconfirm --clean

if [[ -x dist/sm0l/sm0l ]]; then
  echo
  echo "Built: dist/sm0l/sm0l"
  echo "Run with ./run.sh or install with ./install.sh"
else
  echo "BUILD FAILED"
  exit 1
fi
