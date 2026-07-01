#!/usr/bin/env bash
# Build the CiteVahti DESKTOP APP: a supervised macOS app with THREE frozen executables
# inside one bundle —
#   Contents/MacOS/CiteVahti          the shell (Dock icon, menu-bar icon, pywebview window)
#   Contents/MacOS/citevahti-engine   the review-panel sidecar (engine.py)
#   Contents/MacOS/citevahti-mcp      the agent-server sidecar (agent/mcp_server.py)
# The shell spawns and supervises the two sidecars as subprocesses (see supervisor.py) —
# it never runs the panel or the MCP server in its own process. No Python, no browser, and
# (once launched) no Terminal is involved on the user's machine.
#
# Output: build/app/dist/CiteVahti.app (macOS) · CiteVahti.exe (Windows) · CiteVahti/ (Linux)
# — the Windows/Linux builds only freeze the shell today; the sidecar sub-executables and
# menu-bar icon are macOS-only for now (see desktop.py's module docstring).
# Signing + notarization is a SEPARATE step (Developer ID + notarytool, same Apple creds as
# the .mcpb) and runs in CI with the founder's secrets — `codesign --deep` there already
# recurses into every nested executable this script adds, so it needs no changes for the
# extra binaries. This script produces the UNSIGNED bundle. See BUILD.md.
set -euo pipefail
cd "$(dirname "$0")"

# Arg: a PyPI version (e.g. 0.30.0) or "local" to build from THIS checkout.
VERSION="${1:-local}"
BUILD="build/app"
rm -rf "$BUILD" && mkdir -p "$BUILD"

echo "==> Creating isolated build venv ..."
python3 -m venv "$BUILD/venv"
"$BUILD/venv/bin/pip" install --quiet --upgrade pip
# [keyring] is NOT optional here: the panel's "Connect Zotero" and the agent's Zotero
# write path both store/read the key via the OS keychain (credentials.py). A frozen app
# can never be fixed by `pip install keyring` on the user's machine — omitting it here
# shipped a build whose Zotero connect failed at the very last step (after key validation).
if [ "$VERSION" = "local" ]; then
  echo "==> Installing citevahti[app,mcp,keyring] from the local checkout (..) + pyinstaller ..."
  "$BUILD/venv/bin/pip" install --quiet "..[app,mcp,keyring]" pyinstaller
else
  echo "==> Installing citevahti[app,mcp,keyring]==${VERSION} + pyinstaller ..."
  "$BUILD/venv/bin/pip" install --quiet "citevahti[app,mcp,keyring]==${VERSION}" pyinstaller
fi

# App icon: PyInstaller wants .icns on macOS, .ico on Windows; fall back to the panel PNG.
# The path must be ABSOLUTE — PyInstaller resolves --icon relative to the .spec (which we
# write under --specpath build/app), not this script's CWD, so a bare "icon.png" is not found.
ICON_ARG=()
if [ -f icon.icns ]; then ICON_ARG=(--icon "$PWD/icon.icns")
elif [ -f icon.ico ]; then ICON_ARG=(--icon "$PWD/icon.ico")
elif [ -f icon.png ]; then ICON_ARG=(--icon "$PWD/icon.png"); fi

echo "==> Freezing the shell (windowed; panel web assets bundled via --collect-data) ..."
"$BUILD/venv/bin/pyinstaller" --windowed --name CiteVahti \
  --distpath "$BUILD/dist" --workpath "$BUILD/work" --specpath "$BUILD" \
  --osx-bundle-identifier com.vahtian.citevahti \
  --collect-data citevahti \
  --collect-submodules citevahti \
  --collect-all webview \
  "${ICON_ARG[@]}" \
  app/pyi_app_entry.py

# --onedir, not --onefile: measured on-device, a --onefile sidecar re-extracts itself to a
# fresh temp path on EVERY launch, and macOS re-scanning that freshly-written, unique-path
# payload turned every app launch into a ~50s hang before the panel came up — a --onedir
# build (a stable on-disk executable + its files, no per-launch extraction) started in ~1s
# on the same machine. See paths.py's `bundled_binary` docstring.
echo "==> Freezing the citevahti-engine sidecar (review panel + project store) ..."
"$BUILD/venv/bin/pyinstaller" --onedir --name citevahti-engine \
  --distpath "$BUILD/dist-bin" --workpath "$BUILD/work" --specpath "$BUILD" \
  --collect-data citevahti \
  --collect-submodules citevahti \
  --collect-submodules keyring \
  app/pyi_engine_entry.py

# Same PyInstaller flags as build-binary.sh's citevahti-mcp freeze (the .mcpb's binary
# target) — kept in sync deliberately rather than inventing a second way to freeze it —
# except --onedir instead of --onefile, for the same cold-start reason as citevahti-engine
# above (the .mcpb's own citevahti-mcp stays --onefile; that one is spawned per-connection
# by Claude Desktop, a different launch pattern not measured here).
echo "==> Freezing the citevahti-mcp sidecar (agent-server interface) ..."
"$BUILD/venv/bin/pyinstaller" --onedir --name citevahti-mcp \
  --distpath "$BUILD/dist-bin" --workpath "$BUILD/work" --specpath "$BUILD" \
  --collect-submodules mcp.server \
  --collect-data mcp \
  --collect-submodules citevahti \
  --collect-submodules keyring \
  --exclude-module mcp.cli \
  --exclude-module typer \
  server/pyi_entry.py

# Verify the artifacts contain what they claim (silent omission is the classic packaging
# bug — this exact check would have caught the missing-keyring Zotero regression). The
# keyring package must be importable inside BOTH frozen sidecars: the engine stores the
# key at "Connect Zotero", the mcp sidecar reads it for agent-gated writes.
for SIDECAR in citevahti-engine citevahti-mcp; do
  if ! ls "$BUILD/dist-bin/$SIDECAR/_internal/keyring" >/dev/null 2>&1; then
    echo "ERROR: keyring is missing from the frozen $SIDECAR — Zotero connect would fail" >&2
    exit 1
  fi
done
echo "==> verified: keyring frozen into both sidecars"

# Both sidecars live INSIDE the shell's own bundle as whole --onedir folders (three
# executables, one .app) — the shell resolves the nested executable at runtime as a sibling
# of its own `sys.executable` (paths.py's `bundled_binary`), not as a separate top-level .app.
APP="$BUILD/dist/CiteVahti.app"
MACOS_DIR="$APP/Contents/MacOS"
if [ -d "$APP" ]; then
  cp -R "$BUILD/dist-bin/citevahti-engine" "$MACOS_DIR/citevahti-engine"
  cp -R "$BUILD/dist-bin/citevahti-mcp" "$MACOS_DIR/citevahti-mcp"
  chmod +x "$MACOS_DIR/citevahti-engine/citevahti-engine" "$MACOS_DIR/citevahti-mcp/citevahti-mcp"
  echo "==> copied citevahti-engine/ + citevahti-mcp/ into $MACOS_DIR"
fi

# Stamp the real version into the .app Info.plist (PyInstaller defaults it to 0.0.0, which
# would ship a wrong-versioned bundle — the same "which build am I running" bug the .mcpb
# fixed). Read it from the frozen package so it always matches what's inside.
if [ -d "$APP" ]; then
  VER=$("$BUILD/venv/bin/python" -c "import citevahti; print(citevahti.__version__)")
  PL="$APP/Contents/Info.plist"
  # Set if the key exists, else Add — PyInstaller writes CFBundleShortVersionString but not
  # CFBundleVersion, and `Set` on a missing key errors.
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VER" "$PL" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VER" "$PL"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VER" "$PL" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VER" "$PL"
  echo "==> stamped CiteVahti.app version = $VER"
fi

echo "==> App bundle built under $BUILD/dist/"
ls -la "$BUILD/dist" || true
[ -d "$APP" ] && ls -la "$MACOS_DIR" || true
echo "==> Next (CI, founder's Apple creds): codesign --deep --options runtime + notarytool,"
echo "    the same Developer ID flow as the .mcpb. --deep signs the two nested sidecar"
echo "    executables too. This script emits the UNSIGNED bundle."
