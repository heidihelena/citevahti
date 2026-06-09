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

## TODO before distribution
- [x] Route B binary built for **mac arm64** (`server.type: binary`, no Python required). ⚠️ arm64
      only — Intel Macs + Windows/Linux each need their own `build-binary.sh` run on that platform.
- [ ] Add `icon.png` (from the CiteVahti Sentinel mark).
- [ ] Code-sign / notarize the binary so macOS Gatekeeper doesn't block it (Apple Developer
      cert — separate from the git SSH signing key).
- [ ] Confirm Zotero connection works inside the sandboxed extension (API key / OAuth path).
- [ ] Decide the default ledger folder + first-run behaviour.
