---
name: secure-release
description: >-
  The secure front-door for building, developing, releasing, and updating CiteVahti. Use this
  whenever you are about to cut a release or bump the version; build, sign, or notarize the
  desktop app, the .mcpb extension, or the PyInstaller binary; set up or change automatic
  updates (tufup / code signing); add or change an agent/MCP tool or anything touching the
  blinded-rating or Zotero-write path; harden CI, secrets, or the loopback panel; or prepare
  CiteVahti to go from beta toward a production-grade, trustworthy product. Trigger this even
  when the user just says "ship it", "release", "new version", "build the app", "sign it",
  "set up auto-update", or "make this more secure" — the safety gates and release discipline
  here are easy to skip by accident and expensive to get wrong on a clinical-adjacent tool
  used in live pilots.
---

# Secure release & development — CiteVahti

CiteVahti is a local-first, single-user citation-integrity tool used in **live pilots with
real researchers**, handling clinical-adjacent data. That changes the bar: a broken release
or a weakened safety invariant doesn't just annoy a user, it can corrupt a research
provenance trail. This skill is the disciplined path for changing, releasing, and updating it
without breaking the guarantees the product is built on.

The repo already documents the mechanics in depth. This skill is the **orchestration layer**:
it tells you the order, the gates that are easy to skip, and the security defaults — then
points you at the canonical doc for each step. Read the referenced doc before doing that step;
don't reconstruct it from memory.

| Topic | Canonical doc in the repo |
|---|---|
| Publishing the Python package + VS Code extension | `docs/RELEASING.md` |
| Building/signing the desktop app, `.mcpb`, and binary | `desktop-extension/BUILD.md` |
| The hard safety invariants (enforced in code + tests) | `docs/SAFETY_INVARIANTS.md` |
| The secure auto-update model (tufup key split, signing) | `references/secure-updates.md` (this skill) |
| Security practices derived from the threat-model research | `references/security-checklist.md` (this skill) |

## The cardinal rule: gates before mechanics

Every release runs through three gates **in order**. Skipping a gate is the failure mode this
skill exists to prevent.

1. **Safety gate** — did this change weaken a guarantee? (§1)
2. **Build & test gate** — does it pass offline, and do the artifacts actually contain what they should? (§2)
3. **Release & update gate** — version lockstep, signed artifacts, the right trigger. (§3)

---

## §1 — Safety gate (run this BEFORE you even think about releasing)

CiteVahti's value is its guarantees, not its features. `docs/SAFETY_INVARIANTS.md` lists 12
hard invariants (enforced in code, guarded by tests) plus supporting ones. The full suite is
the real enforcement — but these are the ones a change most often erodes silently, so check
them by hand when your change is anywhere near them:

- **Blinded, sealed rating.** The AI support rating is recorded blind and stays hidden until
  the human rates (sealed-envelope). The AI value can *never* auto-become the final value, and
  a discordant record needs explicit adjudication. If you touched `rating/`, `validators/`,
  the panel rating view, or any prompt that orders human-vs-AI work — re-read invariants #4
  and #5 and run `test_dual_rating.py` + `test_rating_validators.py`.
- **Read-only views never mutate the ledger.** `claim_report`, `triage`, `methods_statement`,
  `check_paragraph` append no audit entry and write no file (the methods agreement numbers use
  `AgreementReportService.report(persist=False)`). This has been broken before by a view
  quietly calling a service that writes. If you added or changed a read surface, it MUST be
  covered by `test_readonly_tools_dont_mutate.py`.
- **The agent tool surface is allow-listed.** Adding any MCP/agent tool requires editing
  **both** `src/citevahti/agent/__init__.py` (`TOOLS`) **and** `src/citevahti/agent/policy.py`
  (`ALLOWED_AGENT_TOOLS`). The import-time `assert_safe_surface` guard fails the build if they
  disagree — that's intentional. Never widen the surface to make a tool "just work"; widen it
  deliberately and write down why. A new tool that mutates state or reaches the network needs
  the same scrutiny as a Zotero write.
- **Zotero writes stay dry-run + token-confirmed + undoable** (invariant #8). Don't add a
  write path that bypasses the one-use, payload-bound, expiring token.

**Why this is gate #1:** every other step (build, sign, publish) makes the change *harder to
take back* — once it's signed and auto-pushed to pilot users, a weakened invariant is live in
the field. Catch it here.

If the change adds an out-of-scope security or safety concern you don't want to fix in this
release, note it explicitly rather than letting it ride silently.

---

## §2 — Build & test gate

Everything must pass **offline** — the suite uses fake seams for HTTP/Zotero/BBT/PubMed/the
AI rater, so a green run proves no accidental live call crept in.

```bash
python -m pytest -q                      # full offline suite — must be green
cd vscode-extension && npm run compile   # the VS Code adapter must compile
```

When building distributable artifacts, **verify the artifact contains what it claims** —
silent omission is the classic packaging bug:

- **Wheel** — the panel UI ships as package data. Confirm `citevahti/panel/web/{index.html,
  app.js,styles.css}` are inside the `.whl` (the publish workflow already asserts this; if you
  build locally, run the check in `docs/RELEASING.md`).
- **Desktop app / `.mcpb`** — follow `desktop-extension/BUILD.md`. `build-app.sh` produces the
  **unsigned** PyInstaller bundle; signing is a separate step (§3 + `references/secure-updates.md`).
  After signing a binary, **smoke-test that it still runs** — a hardened runtime + onefile
  freeze can produce a signed binary that won't launch (`sign-notarize.sh` does this check;
  keep it).
- **Manifest parity** — the `.mcpb` advertises prompts in `desktop-extension/manifest.json` +
  `manifest.binary.json`. Adding an MCP prompt means adding it there too, or Claude Desktop
  can't discover it. The parity test guards this; don't hardcode an expected prompt set in the
  test (it silently rots) — derive it from the prompt-name constants.

---

## §3 — Release & update gate (token-free loop)

The release loop is **token-free**: no PyPI secret is stored anywhere. Publishing happens via
PyPI Trusted Publishing (OIDC) when you publish a GitHub Release. `main` is branch-protected
and needs three CI checks green. Read `docs/RELEASING.md` for the full runbook; the steps:

1. **Bump the version in lockstep across all five files** (a mismatch ships a wrong-versioned
   artifact, and the user can't tell what's running — which is exactly the bug 0.34.3 fixed by
   surfacing the version):
   - `pyproject.toml`
   - `src/citevahti/__init__.py` (`__version__`)
   - `vscode-extension/package.json`
   - `desktop-extension/manifest.json`
   - `desktop-extension/manifest.binary.json`
2. **Add the `CHANGELOG.md` `## X.Y.Z` section** and bump the `docs/STATUS.md` header line.
3. **Open a PR off a branch** (never push release commits straight to `main` — it's protected).
   Stage explicit paths; do **not** `git add -A` — this repo carries untracked local/foreign
   files (e.g. `.claude/`, stray `.bib` files) that have been swept into commits before.
4. **Wait for the three required checks**, then squash-merge:
   - `pytest (offline) · py3.10`
   - `pytest (offline) · py3.12`
   - `VS Code extension compiles`
5. **Create the GitHub Release** with tag `vX.Y.Z` targeting main:
   ```bash
   gh release create vX.Y.Z --target main --title "..." --notes "..."
   ```
   This fires `publish-pypi.yml` (builds, `twine check`s, publishes via Trusted Publishing in
   the `pypi` environment) **and** `desktop-extension-build.yml` (builds the signed bundles).
6. **Confirm it actually published** — trust the workflow logs first (the PyPI JSON API lags
   minutes). Then confirm the running version is the new one (the `status` MCP tool reports it).

End commit messages with the `Co-Authored-By: Claude` trailer and PR bodies with the
`Generated with Claude Code` line, per repo convention.

### Updates reach users differently per surface — set expectations honestly

- **Desktop app (the primary product):** there is currently **no auto-updater**. The path to
  one is `tufup` + code signing — see `references/secure-updates.md`. Until that ships, the
  honest UX is a version-check nudge, not a promise of auto-update.
- **`.mcpb` in Claude Desktop:** auto-update exists **only** for extensions in Anthropic's
  curated directory. A privately distributed `.mcpb` requires a manual remove-and-reinstall
  (Claude Desktop caches the old one). So: surface the version in a tool (done in 0.34.3) and
  nudge, until/unless CiteVahti is accepted into the directory. *(Vendor behavior, dated 2026;
  re-check before relying on it.)*
- **PyPI:** technical users `pip install -U`. An in-app "newer version on PyPI" nudge is fine;
  never silently auto-`pip install` — that violates the local-first, no-surprise posture.

---

## §4 — Security defaults (always on)

These aren't release-time extras; they're standing practice. Full detail and the threat-model
reasoning are in `references/security-checklist.md`. The non-negotiables:

- **Secrets never touch git, logs, or chat.** PyPI/Marketplace/signing tokens go in env vars,
  the OS keychain (the `keyring` extra), or GitHub Secrets — never committed, never echoed.
  GitHub Secrets are safe across the planned history rewrite *because they're not in git* —
  keep it that way; never let a keystore or `.env` get committed during the transition.
- **Pin GitHub Actions to a full commit SHA**, not a floating tag. The workflows currently use
  `@v7` / `@release/v1` — a compromised third-party action is the most common way CI secrets
  (your signing keys, once added) leak. Pin them before adding any signing secret to CI.
- **Keep CI least-privilege.** `permissions: contents: read` by default; grant `id-token:
  write` only on the publish job (already the case). Gate any job that holds a signing key
  behind a GitHub Environment with required reviewers, the same way `pypi` is gated.
- **Split signing keys by trust level** (see `references/secure-updates.md`): online roles
  (tufup `timestamp`/`snapshot`) may live in CI; the trust anchors (`root`/`targets`) stay
  offline even in beta. That single split is the whole reason to use tufup over a one-key
  scheme.
- **The loopback panel is already hardened** (`Host`/`Origin`/Content-Type checks in
  `panel/server.py`, guarded by `test_panel_csrf.py`) — localhost is not private (DNS-rebinding,
  CSRF), and those checks are the defense. Any new mutating endpoint inherits them; don't add a
  write path that bypasses `do_POST`'s checks. A per-session token is a deliberate non-goal for
  this single-user threat model. Details in `references/security-checklist.md`.

---

## Honest scope: what "production-grade" means here, and what to get help with

"Flawless" for a single-maintainer clinical-adjacent tool means **trustworthy and
well-bounded**, not feature-complete. Prioritize the guarantees and the update/signing chain;
defer breadth.

Flag these as **real maintenance burdens — get a second pair of eyes / outside help**, don't
silently take them on solo:

- **Signing-key custody and rotation** for tufup (and what happens if a key leaks — `root`
  rotation is the painful one). Write a key-management runbook before the first signed update.
- **Windows code signing under the Vahtian org** (Azure Artifact Signing is token-free and
  cheap for EU *organizations* but not for EU individuals — this is why it goes under Vahtian).
  Confirm the org verification before depending on it.
- **A signed/anchored audit trail.** The current hash-chain is tamper-*evident*, not signed —
  a full re-hash still validates. That's an honest beta posture (documented in
  `SAFETY_INVARIANTS.md`), not a flaw to hide. Upgrading it (RFC 3161 timestamping / signing
  the audit head) is a deliberate, scoped decision for when pilots grow — not a silent default.
