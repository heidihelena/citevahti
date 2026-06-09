#!/usr/bin/env bash
# Route A (prototype): vendor citevahti[mcp] into server/lib and pack a python-type .mcpb.
# For same-machine testing only — relies on the user's system python3 >= 3.10.
# See BUILD.md. Production distribution uses build-binary.sh (no Python needed).
set -euo pipefail
cd "$(dirname "$0")"

VERSION="${1:-0.15.0}"
echo "==> Vendoring citevahti[mcp]==${VERSION} into server/lib ..."
rm -rf server/lib && mkdir -p server/lib
python3 -m pip install --quiet --target server/lib "citevahti[mcp]==${VERSION}"

echo "==> Trimming bundle (tests, caches) ..."
find server/lib -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find server/lib -type d -name "tests" -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> Validating manifest ..."
npx --yes @anthropic-ai/mcpb validate manifest.json

echo "==> Packing dist/citevahti.mcpb ..."
mkdir -p dist
npx --yes @anthropic-ai/mcpb pack . dist/citevahti.mcpb

echo "==> Done. Install dist/citevahti.mcpb via Claude Desktop → Settings → Extensions."
