#!/usr/bin/env bash
# Remove a sm0l install created by install.sh. Does not delete config, sessions, or workspace.
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
LIBDIR="${LIBDIR:-$PREFIX/lib/sm0l}"
BINDIR="${BINDIR:-$PREFIX/bin}"
APPDIR="${APPDIR:-$PREFIX/share/applications}"
ICONDIR="${ICONDIR:-$PREFIX/share/icons/hicolor/256x256/apps}"
SHAREDIR="${SHAREDIR:-$PREFIX/share/sm0l}"

rm -rf "$LIBDIR" "$SHAREDIR"
rm -f "$BINDIR/sm0l" "$APPDIR/sm0l.desktop" "$ICONDIR/sm0l.png"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPDIR" >/dev/null 2>&1 || true
fi

echo "Removed sm0l from $PREFIX"
echo "Left in place: ~/.config/sm0l  ~/.local/share/sm0l  ~/sm0l_workspace"
