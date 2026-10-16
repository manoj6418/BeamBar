#!/bin/bash
# Builds dist/BeamBar.app, then dist/BeamBar-<version>.dmg and .zip for a GitHub release.
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
VERSION=$("$PY" -c "import re; print(re.search(r\"VERSION = '([^']+)'\", open('setup.py').read()).group(1))")
APP=dist/BeamBar.app
DMG=dist/BeamBar-$VERSION.dmg
ZIP=dist/BeamBar-$VERSION.zip

rm -rf build dist
"$PY" setup.py py2app >/dev/null

# Ad-hoc signature: required to run on Apple Silicon. Without a Developer ID the first open
# needs System Settings → Privacy & Security → Open Anyway.
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

STAGE=$(mktemp -d)
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "BeamBar $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO "$DMG"
rm -rf "$STAGE"

ditto -c -k --keepParent "$APP" "$ZIP"

shasum -a 256 "$DMG" "$ZIP"
du -sh "$APP" "$DMG" "$ZIP"
