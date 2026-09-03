#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PREFIX="$(mktemp -d /tmp/sm0l_prefix.XXXXXX)"
export PREFIX
chmod +x install.sh uninstall.sh
./install.sh
test -x "$PREFIX/bin/sm0l"
test -f "$PREFIX/share/applications/sm0l.desktop"
test -f "$PREFIX/share/icons/hicolor/256x256/apps/sm0l.png"
test -f "$PREFIX/lib/sm0l/sm0l.py"
test -x "$PREFIX/lib/sm0l/.venv/bin/python"
grep -F "$PREFIX/lib/sm0l/sm0l.py" "$PREFIX/bin/sm0l" >/dev/null
echo "install layout ok at $PREFIX"
export QT_QPA_PLATFORM=offscreen
export PYTHONPATH="$PREFIX/lib/sm0l"
"$PREFIX/lib/sm0l/.venv/bin/python" -c "from PyQt6.QtWidgets import QApplication; import sys; app=QApplication(sys.argv); from src.paths import config_path, user_data; print('qt ok'); print(config_path()); print(user_data())"
echo "INSTALL SMOKE OK"
