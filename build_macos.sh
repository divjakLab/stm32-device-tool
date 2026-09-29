#!/bin/bash
# ---------------------------------------------------------------------------
# Builds  output/STM32DeviceTool-<version>.dmg
#
# Needs on the build Mac: Python 3.13 (Homebrew python@3.13 or python.org).
# Optional, for distribution without Gatekeeper warnings:
#   export SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID)"
#   export NOTARY_PROFILE="my-notary-profile"
#       (created once with: xcrun notarytool store-credentials ...)
# The app is built for the CPU of the build Mac (Apple Silicon -> arm64).
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

VERSION="1.0.0"
APP="dist/STM32 Device Tool.app"
DMG="output/STM32DeviceTool-${VERSION}.dmg"
PY="${PYTHON:-python3.13}"

[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements-build.txt

python -m pytest -q
[ -f resources/icon.icns ] || python tools/make_icon.py

rm -rf build dist
pyinstaller --noconfirm device_tool.spec

"$APP/Contents/MacOS/STM32DeviceTool" --selftest | tee selftest.log
grep -q "SELFTEST PASSED" selftest.log

if [ -n "${SIGN_IDENTITY:-}" ]; then
    codesign --force --deep --options runtime --timestamp \
        --entitlements entitlements.plist --sign "$SIGN_IDENTITY" "$APP"
    codesign --verify --deep --strict --verbose=2 "$APP"
else
    echo "NOTE: no SIGN_IDENTITY - ad-hoc signing (users right-click → Open the first time)"
    codesign --force --deep --sign - "$APP"
fi

mkdir -p output
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "STM32 Device Tool" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

if [ -n "${SIGN_IDENTITY:-}" ] && [ -n "${NOTARY_PROFILE:-}" ]; then
    codesign --sign "$SIGN_IDENTITY" --timestamp "$DMG"
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG"
fi

echo "Done: $DMG"
