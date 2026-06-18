# CiteVahti Claude Desktop Extension (`.mcpb`)

Goal: a **double-click install** for non-technical researchers — no terminal, no `pip`,
no MCP-JSON editing. User downloads `citevahti.mcpb`, opens it, Claude Desktop installs it,
they pick a folder, done.

The manifest is validated (`mcpb validate manifest.json` → passes). The launch command is
the package's own stdio MCP entry point: `citevahti-mcp --root <ledger dir>`.

## The one real decision: how Python ships

CiteVahti is a Python package, so the bundle has to deal with the Python runtime. Two routes:

### Route A — `python` type (dev/test prototype) — `build-python.sh`
Vendors `citevahti[mcp]` into `server/lib/` and lets Claude Desktop run it with the user's
**system `python3`**.
- ✅ Fast to build; good for validating the flow on a machine that already has Python ≥3.10.
- ❌ **Not safe for the target user.** Relies on the user having `python3` ≥3.10 on PATH, and
  the vendored compiled wheels (e.g. `pydantic-core`) are tied to one Python version + CPU
  arch. A non-technical user with no/old Python — the whole reason we're doing this — breaks.
- Use only for your own end-to-end testing.

### Route B — `binary` type (production) — `build-binary.sh`  ← target for real distribution
PyInstaller freezes `citevahti-mcp` into a **self-contained executable** (Python bundled
inside). Manifest switches to `server.type: "binary"`, `command: "${__dirname}/server/citevahti-mcp"`.
- ✅ **No Python needed on the user's machine at all** — the actual no-terminal goal.
- ❌ One build per platform/arch (mac arm64 first; then mac x64, win, linux). Larger file.
  Needs hidden-import shims for `mcp` / `starlette` / `uvicorn`.

**Recommendation:** prototype with Route A to prove the install + tools flow in your own
Claude Desktop, then ship Route B (start with mac arm64, the founder's machine).

## Build (Route A, prototype)
```
./build-python.sh        # vendors deps into server/lib, packs dist/citevahti.mcpb
```
Then in Claude Desktop: Settings → Extensions → install from file → pick `dist/citevahti.mcpb`,
set the CiteVahti folder when prompted.

## Build (Route B, production)
```
./build-binary.sh        # PyInstaller freeze → server/citevahti-mcp, packs dist/citevahti.mcpb
```
Uses `manifest.binary.json` (staged, so the tracked `manifest.json` stays the python variant).
The build *produces* `server/citevahti-mcp`; on the build machine that binary was confirmed to
run under `env -i` (no PATH, no Python) — self-contained.

> **Not in the checkout.** The binary and `dist/*.mcpb` are **gitignored build artifacts**, so a
> fresh clone has neither until you run `./build-binary.sh` (or download a release asset).
> `manifest.binary.json` points at the path the build creates. To let others install-test the
> no-Python claim without building, attach `dist/citevahti.mcpb` to a GitHub Release (mark it
> arm64 + un-notarized).

## Signing macOS in CI (GitHub Actions)

`sign-notarize.sh` is the **local** path (keychain profile). To have every release build a
signed + notarized macOS `.mcpb` automatically, the `macos` job in
[`desktop-extension-build.yml`](../.github/workflows/desktop-extension-build.yml) does the same
in CI — gated on six repo secrets (Settings → Secrets and variables → Actions). You already hold
the Developer ID (`Developer ID Application: Heidi Andersen (FZQ347J9NX)`); CI just needs it as
secrets:

| Secret | How to get it |
|---|---|
| `MACOS_CERT_P12_BASE64` | Keychain Access → export the Developer ID Application cert as `.p12`, then `base64 -i cert.p12 \| pbcopy` |
| `MACOS_CERT_PASSWORD` | the password you set on that `.p12` export |
| `MACOS_SIGN_IDENTITY` | `Developer ID Application: Heidi Andersen (FZQ347J9NX)` |
| `MACOS_NOTARY_KEY_P8` | App Store Connect → Users and Access → Integrations → Keys → create an API key; download the `.p8`, then **base64 it** (PEM newlines don't survive a raw paste → `invalidP8`): `base64 -i AuthKey_XXXXXXXX.p8 \| pbcopy` |
| `MACOS_NOTARY_KEY_ID` | the key id shown next to that key |
| `MACOS_NOTARY_ISSUER` | the Issuer ID on the Keys page |

Until the secrets exist the `macos` job builds an **unsigned** bundle as a CI artifact only
(never attached to a release). Once they're set, every published release — and a manual
`workflow_dispatch` with `release_tag: vX.Y.Z` to backfill an existing one — attaches
`citevahti-<version>-macos-arm64.mcpb`, signed + notarized. (A `.mcpb` zip can't be stapled, so
Gatekeeper verifies the ticket online on first launch — fine for connected machines.)

## TODO before distribution
- [x] Route B binary built for **mac arm64** (`server.type: binary`, no Python required). ⚠️ arm64
      only — Intel Macs + Windows/Linux each need their own `build-binary.sh` run on that platform.
- [ ] Add `icon.png` (from the CiteVahti Sentinel mark).
- [x] **Code-sign + notarize — DONE (mac arm64, 2026-06-09).** Binary signed with
      `Developer ID Application: Heidi Andersen (FZQ347J9NX)` (hardened runtime + entitlements
      + secure timestamp), `.mcpb` re-packed with the signed binary, submitted via
      `xcrun notarytool submit … --keychain-profile citevahti-notary --wait` → **status:
      Accepted** (submission `1b56ad58-0946-4afd-be6d-a5ef53b8f254`). Re-run any time with
      `SIGN_IDENTITY="Developer ID Application: Heidi Andersen (FZQ347J9NX)" ./sign-notarize.sh`.
      Caveat: a `.mcpb` (zip) can't be stapled → Gatekeeper checks notarization online on first
      launch; for offline-proof, ship a signed+notarized `.pkg` instead. Onefile + hardened
      runtime is fragile — if the signed binary won't launch, rebuild `--onedir` and sign nested libs.
- [ ] Confirm Zotero connection works inside the sandboxed extension (API key / OAuth path).
- [ ] Decide the default ledger folder + first-run behaviour.
- [x] **Rebuilt with `open_review_panel` — signed + notarized (2026-06-12).** Built from
      the local checkout (`./build-binary.sh local`, manifest `0.16.0-beta.1`), MCP smoke
      test confirms all 13 tools incl. `open_review_panel`, signed with the FZQ347J9NX
      Developer ID, notarized **Accepted** (submission `28db1e09-6929-42b3-8dcb-cf6ccf13de37`;
      ticket covers `server/citevahti-mcp`, arm64). Artifact: `dist/citevahti.mcpb` — attach
      to the GitHub release the README install box points at. Background (added 2026-06-12): The bare stdio
      server used to dead-end the no-terminal path at the rate-first step — the
      prompt sent the human to a localhost panel nothing had launched. The agent
      surface now has an `open_review_panel` tool (idempotent, loopback-only,
      opens the browser), and the `run_claim_tests` prompt step 7 tells the model
      to call it. Any binary built before that date still has the dead-end:
      rebuild with `./build-binary.sh`, then re-run sign-notarize.
