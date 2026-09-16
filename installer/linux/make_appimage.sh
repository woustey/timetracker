#!/bin/sh
# Wrap the Nuitka standalone directory into an AppImage (PRD-02 §12.2).
#   installer/linux/make_appimage.sh dist/release/linux/timetracker.dist 1.0.0
set -eu
DIST="$1"
VERSION="$2"
OUT="dist/installer"
mkdir -p "$OUT"
APPDIR="$(mktemp -d)/TimeTracker.AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -R "$DIST"/. "$APPDIR/usr/bin/"
cp installer/linux/AppRun "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun" "$APPDIR/usr/bin/timetracker.bin"
cp installer/linux/timetracker.desktop "$APPDIR/timetracker.desktop"
cp src/timetracker/resources/icon-256.png "$APPDIR/timetracker.png"
cp src/timetracker/resources/icon-256.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/timetracker.png"
if [ ! -x appimagetool ]; then
  curl -L -o appimagetool "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x appimagetool
fi
ARCH=x86_64 ./appimagetool --appimage-extract-and-run "$APPDIR" "$OUT/TimeTracker-$VERSION-x86_64.AppImage"
echo "built $OUT/TimeTracker-$VERSION-x86_64.AppImage"
