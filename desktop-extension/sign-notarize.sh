#!/usr/bin/env bash
# Sign + notarize the CiteVahti desktop binary so macOS Gatekeeper won't block it
# when Claude Desktop runs it on someone else's machine.
#
# ⚠️ UNTESTED until a Developer ID cert exists (we have 0 signing identities now).
#    Run ./build-binary.sh first to produce server/citevahti-mcp.
#
# ONE-TIME PREREQUISITES (founder, can't be automated):
#   1. Apple Developer Program enrollment ($99/yr).
#   2. A "Developer ID Application" certificate in the login keychain.
#        check:  security find-identity -v -p codesigning   # must list "Developer ID Application: …"
#   3. notarytool credentials saved once under a profile name:
#        xcrun notarytool store-credentials citevahti-notary \
#          --apple-id "you@apple.id" --team-id "TEAMID" --password "APP-SPECIFIC-PASSWORD"
#      (app-specific password: appleid.apple.com → Sign-In & Security → App-Specific Passwords)
#
# USAGE:
#   SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" ./sign-notarize.sh
set -euo pipefail
cd "$(dirname "$0")"

IDENTITY="${SIGN_IDENTITY:?set SIGN_IDENTITY to your 'Developer ID Application: Name (TEAMID)' string (see: security find-identity -v -p codesigning)}"
PROFILE="${NOTARY_PROFILE:-citevahti-notary}"
BIN="server/citevahti-mcp"
[ -f "$BIN" ] || { echo "no binary — run ./build-binary.sh first"; exit 1; }

echo "==> codesign (Developer ID + hardened runtime + entitlements + secure timestamp)"
codesign --force --options runtime --timestamp \
  --entitlements entitlements.plist --sign "$IDENTITY" "$BIN"
codesign --verify --strict --verbose=2 "$BIN"
# sanity: confirm the binary STILL RUNS after signing (onefile + hardened runtime can break it)
echo "==> post-sign smoke test (must still print help):"
"./$BIN" --help >/dev/null && echo "   OK — signed binary runs" || { echo "   FAILED — signed binary won't run; revisit entitlements / consider --onedir"; exit 1; }
echo "==> post-sign smoke test (panel over MCP stdio) — before spending a notary round-trip:"
python3 smoke_frozen_panel.py "$BIN"

echo "==> re-pack the .mcpb so it contains the SIGNED binary"
STAGE="build/stage-signed"
rm -rf "$STAGE" && mkdir -p "$STAGE/server"
cp manifest.binary.json "$STAGE/manifest.json"
cp "$BIN" "$STAGE/server/citevahti-mcp"
[ -f icon.png ] && cp icon.png "$STAGE/icon.png" || true
mkdir -p dist
npx --yes @anthropic-ai/mcpb pack "$STAGE" dist/citevahti.mcpb

echo "==> notarize (.mcpb submitted as a zip; --wait blocks until Apple responds)"
xcrun notarytool submit dist/citevahti.mcpb --keychain-profile "$PROFILE" --wait

echo
echo "==> DONE if status above is 'Accepted'."
echo "    NOTE: a .mcpb (zip) cannot be stapled (stapler only does .app/.pkg/.dmg), so the"
echo "    notarization ticket lives on Apple's servers — Gatekeeper checks it ONLINE on first"
echo "    launch. That's fine for connected machines. For an offline-proof ticket, ship the"
echo "    binary inside a signed+notarized .pkg instead and staple that."
echo "    Verify the signature:  codesign -dv --verbose=4 $BIN"
echo "    Gatekeeper assess:     spctl -a -t exec -vv $BIN"
