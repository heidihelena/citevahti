#!/usr/bin/env bash
# Route B (production): freeze citevahti-mcp into a standalone executable with PyInstaller,
# so the end user needs NO Python installed. Build once per platform/arch.
# See BUILD.md. Output: server/citevahti-mcp (referenced by manifest.binary.json).
set -euo pipefail
cd "$(dirname "$0")"

# Arg: a PyPI version (e.g. 0.15.0) or "local" to build from THIS checkout —
# use "local" for changes not yet released to PyPI (else you freeze old code).
VERSION="${1:-local}"
BUILD="build/pyi"
rm -rf "$BUILD" && mkdir -p "$BUILD"

echo "==> Creating isolated build venv ..."
python3 -m venv "$BUILD/venv"
"$BUILD/venv/bin/pip" install --quiet --upgrade pip
if [ "$VERSION" = "local" ]; then
  echo "==> Installing citevahti[mcp] from the local checkout (..) + pyinstaller ..."
  "$BUILD/venv/bin/pip" install --quiet "..[mcp]" pyinstaller
else
  echo "==> Installing citevahti[mcp]==${VERSION} + pyinstaller ..."
  "$BUILD/venv/bin/pip" install --quiet "citevahti[mcp]==${VERSION}" pyinstaller
fi

echo "==> Freezing standalone binary ..."
"$BUILD/venv/bin/pyinstaller" --onefile --name citevahti-mcp \
  --distpath "$BUILD/dist" --workpath "$BUILD/work" --specpath "$BUILD" \
  --collect-submodules mcp.server \
  --collect-data mcp \
  --collect-submodules citevahti \
  --exclude-module mcp.cli \
  --exclude-module typer \
  server/pyi_entry.py

cp "$BUILD/dist/citevahti-mcp" server/citevahti-mcp
chmod +x server/citevahti-mcp
echo "==> Binary at server/citevahti-mcp"

echo "==> Smoke test (--help) ..."
server/citevahti-mcp --help || { echo "BINARY SMOKE TEST FAILED"; exit 1; }

echo "==> Staging binary bundle (keeps tracked manifest.json untouched) ..."
STAGE="build/stage"
rm -rf "$STAGE" && mkdir -p "$STAGE/server"
cp manifest.binary.json "$STAGE/manifest.json"
cp server/citevahti-mcp "$STAGE/server/citevahti-mcp"
[ -f icon.png ] && cp icon.png "$STAGE/icon.png" || true

echo "==> Validating + packing binary .mcpb ..."
npx --yes @anthropic-ai/mcpb validate "$STAGE/manifest.json"
mkdir -p dist
npx --yes @anthropic-ai/mcpb pack "$STAGE" dist/citevahti.mcpb
echo "==> Done: dist/citevahti.mcpb (no Python required on the user's machine)."
