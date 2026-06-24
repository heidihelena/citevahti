#!/usr/bin/env bash
# Build the CiteVahti DESKTOP APP: freeze the loopback panel + the native OS webview into
# a windowed, double-clickable bundle with PyInstaller, so the user needs NO Python and NO
# browser. Companion to build-binary.sh (which freezes the stdio MCP server for the .mcpb).
#
# Output: build/app/dist/CiteVahti.app (macOS) · CiteVahti.exe (Windows) · CiteVahti/ (Linux).
# Signing + notarization is a SEPARATE step (Developer ID + notarytool, same Apple creds as
# the .mcpb) and runs in CI with the founder's secrets — this script produces the UNSIGNED
# bundle. See BUILD.md.
set -euo pipefail
cd "$(dirname "$0")"

# Arg: a PyPI version (e.g. 0.30.0) or "local" to build from THIS checkout.
VERSION="${1:-local}"
BUILD="build/app"
rm -rf "$BUILD" && mkdir -p "$BUILD"

echo "==> Creating isolated build venv ..."
python3 -m venv "$BUILD/venv"
"$BUILD/venv/bin/pip" install --quiet --upgrade pip
if [ "$VERSION" = "local" ]; then
  echo "==> Installing citevahti[app] from the local checkout (..) + pyinstaller ..."
  "$BUILD/venv/bin/pip" install --quiet "..[app]" pyinstaller
else
  echo "==> Installing citevahti[app]==${VERSION} + pyinstaller ..."
  "$BUILD/venv/bin/pip" install --quiet "citevahti[app]==${VERSION}" pyinstaller
fi

# App icon: PyInstaller wants .icns on macOS, .ico on Windows; fall back to the panel PNG.
ICON_ARG=()
if [ -f icon.icns ]; then ICON_ARG=(--icon icon.icns)
elif [ -f icon.ico ]; then ICON_ARG=(--icon icon.ico)
elif [ -f icon.png ]; then ICON_ARG=(--icon icon.png); fi

echo "==> Freezing windowed app (panel web assets bundled via --collect-data) ..."
"$BUILD/venv/bin/pyinstaller" --windowed --name CiteVahti \
  --distpath "$BUILD/dist" --workpath "$BUILD/work" --specpath "$BUILD" \
  --collect-data citevahti \
  --collect-submodules citevahti \
  --collect-all webview \
  "${ICON_ARG[@]}" \
  app/pyi_app_entry.py

echo "==> App bundle built under $BUILD/dist/"
ls -la "$BUILD/dist" || true
echo "==> Next (CI, founder's Apple creds): codesign --deep --options runtime + notarytool,"
echo "    the same Developer ID flow as the .mcpb. This script emits the UNSIGNED bundle."
