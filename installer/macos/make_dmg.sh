#!/bin/sh
# Build an unsigned DMG around the Nuitka .app (PRD-02 §12.2).
#   installer/macos/make_dmg.sh "dist/release/macos/Time Tracker.app" 1.0.0
set -eu
APP="$1"
VERSION="$2"
OUT="dist/installer"
mkdir -p "$OUT"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Time Tracker" -srcfolder "$STAGE" -ov -format UDZO "$OUT/TimeTracker-$VERSION.dmg"
rm -rf "$STAGE"
echo "built $OUT/TimeTracker-$VERSION.dmg (unsigned: Gatekeeper will warn, see docs/RELEASE-CHECKLIST.md)"
