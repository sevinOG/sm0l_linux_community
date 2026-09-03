#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -x dist/sm0l/sm0l ]]; then
  exec dist/sm0l/sm0l "$@"
fi

if [[ ! -x .venv/bin/python ]]; then
  if ! python3 -c "import venv, ensurepip" >/dev/null 2>&1; then
    echo "Python venv is required (ensurepip missing)."
    echo "Debian/Ubuntu: sudo apt install python3-venv python3-pip"
    echo "Fedora:        sudo dnf install python3-virtualenv"
    exit 1
  fi
  python3 -m venv .venv
  .venv/bin/python -m pip install -U pip
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python sm0l.py "$@"
