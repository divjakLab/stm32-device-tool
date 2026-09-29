#!/bin/bash
# Packs the source folder for building on a Windows PC:
#     output/STM32DeviceTool-windows-build-kit.zip
# Unzip it on Windows and double-click build_windows.bat.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p output
KIT="output/STM32DeviceTool-windows-build-kit.zip"
rm -f "$KIT"
zip -qr "$KIT" . -x ".venv/*" "build/*" "dist/*" "output/*" "*__pycache__*" \
    ".pytest_cache/*" "selftest.log" ".DS_Store" "*/.DS_Store"
echo "Done: $KIT"
