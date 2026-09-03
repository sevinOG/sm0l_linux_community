#!/usr/bin/env bash
# Install sm0l into an FHS prefix.
#   PREFIX=$HOME/.local ./install.sh     (default, user install)
#   PREFIX=/usr/local sudo ./install.sh  (system install)
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

PREFIX="${PREFIX:-$HOME/.local}"
LIBDIR="${LIBDIR:-$PREFIX/lib/sm0l}"
BINDIR="${BINDIR:-$PREFIX/bin}"
APPDIR="${APPDIR:-$PREFIX/share/applications}"
ICONDIR="${ICONDIR:-$PREFIX/share/icons/hicolor/256x256/apps}"
SHAREDIR="${SHAREDIR:-$PREFIX/share/sm0l}"

mkdir -p "$LIBDIR" "$BINDIR" "$APPDIR" "$ICONDIR" "$SHAREDIR/assets"

install_icon() {
  local src=""
  if [[ -f "$ROOT/assets/icon.png" ]]; then
    src="$ROOT/assets/icon.png"
  elif [[ -f "$LIBDIR/_internal/assets/icon.png" ]]; then
    src="$LIBDIR/_internal/assets/icon.png"
  elif [[ -f "$LIBDIR/assets/icon.png" ]]; then
    src="$LIBDIR/assets/icon.png"
  fi
  if [[ -n "$src" ]]; then
    cp -f "$src" "$ICONDIR/sm0l.png"
    cp -f "$src" "$SHAREDIR/assets/icon.png"
  fi
}

install_desktop() {
  local exec_path="$BINDIR/sm0l"
  local icon_name="sm0l"
  if [[ -f "$ROOT/packaging/sm0l.desktop" ]]; then
    sed -e "s|@EXEC@|$exec_path|g" -e "s|@ICON@|$icon_name|g" \
      "$ROOT/packaging/sm0l.desktop" > "$APPDIR/sm0l.desktop"
  else
    cat > "$APPDIR/sm0l.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=sm0l
Comment=Tiny local Ollama coding agent
Exec=$exec_path
Icon=$icon_name
Terminal=false
Categories=Development;Utility;
StartupWMClass=sm0l
EOF
  fi
  chmod 644 "$APPDIR/sm0l.desktop"
}

if [[ -x "$ROOT/dist/sm0l/sm0l" ]]; then
  echo "Installing frozen binary to $LIBDIR"
  rm -rf "$LIBDIR"
  mkdir -p "$(dirname "$LIBDIR")"
  cp -a "$ROOT/dist/sm0l" "$LIBDIR"
  chmod +x "$LIBDIR/sm0l"
  ln -sfn "$LIBDIR/sm0l" "$BINDIR/sm0l"
else
  echo "No dist/sm0l/sm0l — installing from source into $LIBDIR"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required."
    exit 1
  fi
  if ! python3 -c "import venv, ensurepip" >/dev/null 2>&1; then
    echo "Python venv is required (ensurepip missing)."
    echo "Debian/Ubuntu: sudo apt install python3-venv python3-pip"
    echo "Fedora:        sudo dnf install python3-virtualenv"
    echo "Or run ./build.sh first and re-run ./install.sh to install the frozen binary."
    exit 1
  fi
  rm -rf "$LIBDIR"
  mkdir -p "$LIBDIR"
  cp -a "$ROOT/sm0l.py" "$ROOT/src" "$ROOT/assets" "$ROOT/VERSION" "$ROOT/requirements.txt" "$LIBDIR/"
  python3 -m venv "$LIBDIR/.venv"
  "$LIBDIR/.venv/bin/python" -m pip install -U pip
  "$LIBDIR/.venv/bin/python" -m pip install -r "$LIBDIR/requirements.txt"
  cat > "$BINDIR/sm0l" <<EOF
#!/usr/bin/env bash
exec "$LIBDIR/.venv/bin/python" "$LIBDIR/sm0l.py" "\$@"
EOF
  chmod +x "$BINDIR/sm0l"
fi

install_icon
install_desktop

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPDIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "$(dirname "$(dirname "$ICONDIR")")" >/dev/null 2>&1 || true
fi

echo
echo "Installed sm0l"
echo "  binary : $BINDIR/sm0l"
echo "  lib    : $LIBDIR"
echo "  desktop: $APPDIR/sm0l.desktop"
echo "  icon   : $ICONDIR/sm0l.png"
echo "  config : \${XDG_CONFIG_HOME:-\$HOME/.config}/sm0l/config.json"
echo "  data   : \${XDG_DATA_HOME:-\$HOME/.local/share}/sm0l/"
echo "  workspace default: \$HOME/sm0l_workspace"
echo
if [[ ":$PATH:" != *":$BINDIR:"* ]]; then
  echo "Note: $BINDIR is not on PATH. Add it, or run: $BINDIR/sm0l"
fi
