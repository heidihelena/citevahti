---
name: citevahti-release
description: Use when shipping a CiteVahti release — cutting a version, checking feature parity across the MCP server, desktop extension (.mcpb), loopback panel, and VS Code extension, bumping versions in lockstep, writing the changelog entry, minting the release DOI, or preparing rollback notes. Maintainer-facing. Runs the citevahti-eval accuracy gate first and defers all build/sign/publish mechanics to the secure-release skill and docs/RELEASING.md.
---

# CiteVahti release — parity and shipping

This skill is the release *checklist*, not the release *mechanics*. The mechanics —
safety gate, offline build/test gate, signing, Trusted Publishing — live in the
**`secure-release`** skill (`.claude/skills/secure-release/SKILL.md`) and its canonical
docs (`docs/RELEASING.md`, `desktop-extension/BUILD.md`, `docs/SAFETY_INVARIANTS.md`).
**Read secure-release and run its three gates in order; this skill adds the
production-push gates around them.** Never reconstruct either from memory.

## Triggers

**Use when the maintainer asks to:** cut/ship/tag a release, bump the version, check
surface parity before shipping, write release notes, mint a DOI for a release, or
prepare rollback notes.

**Do NOT use for:** day-to-day development (no release intent), or the accuracy
measurement itself (`citevahti-eval` — this skill only *consumes* its verdict).

## Release order — gates before mechanics

### Gate 0 — the eval gate (production-push addition)

Once acceptance thresholds are pre-registered in `validation/claimcheck/`, **every
release starts by checking the `citevahti-eval` verdict**: a scored ledger at or above
every pre-registered floor, measured on (or unchanged since) the code being released.

- No scored ledger, or any floor missed → **stop. No release.** File the gap.
- Pass → record the numbers; they ship with the release notes and the eval-results page.

*(Until thresholds are first pre-registered, note explicitly in the release notes that
the release predates the accuracy gate — don't let the gap ride silently.)*

### Gates 1–3 — safety, build/test, release/update

These are `secure-release` §1–§3, unchanged and in order:

1. **Safety gate** — did the change weaken an invariant? (`docs/SAFETY_INVARIANTS.md`)
2. **Build & test gate** — full offline suite, `pytest -m security`, VS Code compile,
   artifact-contents checks, smoke-run of frozen artifacts.
3. **Release & update gate** — six-file version lockstep (`pyproject.toml`,
   `src/citevahti/__init__.py`, `vscode-extension/package.json`,
   `desktop-extension/manifest.json`, `desktop-extension/manifest.binary.json`,
   `.claude-plugin/plugin.json`), `CHANGELOG.md` section + `docs/STATUS.md` header,
   PR off a branch with explicit staged paths, three required checks, squash-merge,
   `gh release create vX.Y.Z` → Trusted Publishing + desktop builds, then confirm the
   published version actually reports itself.

### Gate 4 — surface parity (production-push addition)

CiteVahti ships one product through several doors. Before tagging, check each shipped
feature's story on every surface — parity means *accounted for*, not necessarily
*identical*:

| Surface | Where its surface is declared |
|---|---|
| MCP server (tools + prompts) | `src/citevahti/agent/__init__.py` (`TOOLS`) + `policy.py` (`ALLOWED_AGENT_TOOLS`) |
| Desktop extension `.mcpb` | `desktop-extension/manifest.json` + `manifest.binary.json` (prompt/manifest parity test) |
| Loopback panel | `src/citevahti/panel/` (ships as package data — wheel check) |
| VS Code extension | `vscode-extension/package.json` (commands) |
| Claude Code plugin skills | `.claude-plugin/plugin.json` `skills` list vs `skills/` dirs |

For each user-visible change in this release: which surfaces get it, which
intentionally don't, and is any intentional gap noted in the changelog? A feature that
silently exists on one surface only is how the "abandoned adapter" impression starts.

### Gate 5 — DOI + rollback notes (production-push addition)

- **Zenodo DOI per release.** `CITATION.cff` is committed (entity author; **no `version`
  field on purpose** — Zenodo derives the version and date from the release tag, so it is
  *not* a seventh lockstep file). One one-time step remains: enable the repo at
  zenodo.org/account/settings/github. After that each GitHub Release auto-mints a
  versioned DOI under a stable concept DOI. Until that toggle is flipped this step is a
  no-op — note it in the release PR so it doesn't silently drop off. Once live: check that
  the DOI resolves, put the **concept** DOI in `README.md` (and, if you add a
  preferred-citation DOI to `CITATION.cff`, the concept DOI there), and the **versioned**
  DOI in the release notes.
- **Rollback notes.** One short block in the release notes: the last-known-good
  version, and the per-surface downgrade path — PyPI: `pip install citevahti==X.Y.Z`;
  `.mcpb`: remove + reinstall the prior release asset (Claude Desktop caches — a
  re-add of the same file is not enough); VS Code: install the prior `.vsix`.
  State whether the release migrates any on-disk state (ledger/audit formats) and, if
  so, whether downgrade is safe. If a data migration can't be rolled back, say so in
  bold — that's the one thing a pilot user must know before updating.

## Hard rules

- **NEVER ship on a failed or missing eval gate** once thresholds are pre-registered.
- **NEVER skip or reorder the secure-release gates** — signing and publishing make
  mistakes progressively harder to take back.
- **NEVER `git add -A`** on a release commit; stage explicit paths.
- **NEVER hand-edit a version in fewer than all six lockstep files.**
- **NEVER promise auto-update.** The desktop app has no auto-updater yet, and a private
  `.mcpb` needs manual remove-and-reinstall — the honest UX is a version nudge
  (see secure-release §3).
