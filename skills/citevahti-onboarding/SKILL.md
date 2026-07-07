---
name: citevahti-onboarding
description: Use when writing or regenerating CiteVahti install and quickstart documentation for a distribution channel — the desktop app, the .mcpb in Claude Desktop, MCP config for Claude Code or other clients, the VS Code extension, or pip — or when checking that channel docs still match the shipped release. Maintainer-facing; produces docs, it does not onboard a specific user live (walk them through docs/QUICKSTART.md for that).
---

# CiteVahti onboarding — per-channel quickstart generation

One product, several doors: desktop app, `.mcpb` in Claude Desktop, MCP stdio in Claude
Code / other clients, VS Code extension, plain pip + panel. Each door needs its own
first-ten-minutes doc, and those docs rot every release. This skill regenerates them
from the shipped truth instead of from memory.

**Sequencing gate (from `docs/BETA_TO_PRODUCTION.md`):** hold large doc regeneration
until `citevahti-eval` and `citevahti-release` outputs are stable — docs churn before
that is wasted. Fixing a doc that's actively wrong is always in scope.

## Triggers

**Use when the maintainer asks to:** write/refresh a channel quickstart, update
`docs/QUICKSTART.md` after a release, document a new distribution channel, or check
that channel docs still match the current version.

**Do NOT use for:** live-helping one user (use `docs/QUICKSTART.md` +
`citevahti-dev`'s troubleshooting table), or marketing copy (`citevahti-claims`
audits that; this skill writes instructions).

## Sources of truth — generate FROM these, never from memory

| Fact | Source |
|---|---|
| Install paths + exact commands | `docs/QUICKSTART.md` (canonical), `README.md` |
| Channel-specific setup | `skills/citevahti-dev/SKILL.md` §Setup paths A/B/C |
| What's in the current release | `CHANGELOG.md` top section, `docs/STATUS.md` |
| Safety framing users must see | `docs/DISCLOSURE.md`, `docs/KNOWN_LIMITATIONS.md` |
| Update path per channel | secure-release §3 (no auto-update; per-surface manual paths) |

## Per-channel skeleton

Every channel quickstart contains, in order:

1. **Who this path is for** (one line — e.g. "Mac, no terminal" vs "Claude Code user").
2. **What CiteVahti is and isn't** — reuse the `docs/QUICKSTART.md` boxed paragraph
   verbatim (human decides; no silent writes; local-first with outbound literature
   lookups only; beta). Don't paraphrase it — paraphrase is where overclaiming creeps
   in, and `citevahti-claims` audits these docs too.
3. **Install** — copy-pasteable, nothing to memorize, tested against the current
   release on that channel.
4. **First success in ≤10 minutes** — one real claim checked end to end, or
   `citevahti demo` for the nothing-real path.
5. **Connect Zotero** (optional step, panel-driven) and **AI second opinion** setup.
6. **Where things go wrong** — link the troubleshooting table; don't fork it.
7. **How you'll get updates** — honest per-channel story: pip upgrade command; `.mcpb`
   remove-and-reinstall; version nudge for the desktop app. Never promise auto-update.

Channel notes: **Desktop app** — easiest path, macOS; signing/notarization already
covered by the build docs. **Claude Desktop `.mcpb`** — double-click, pick folder; also
the Windows/Linux no-terminal path. **Claude Code / MCP clients** — the Path B block
(`pip install "citevahti[keyring,mcp]"` → `citevahti init` → `citevahti onboard` →
`claude mcp add citevahti -- citevahti start --root …`); note that `citevahti start`
blocking the terminal is correct. **VS Code** — `.vsix` install + `citevahti.cliPath`.
**Panel-only** — `citevahti-panel` for hands-on terminal-adjacent use.

## Checks before publishing a doc

- Run every command block on the channel it documents (or in the closest CI-equivalent);
  a quickstart with one wrong command costs more trust than no quickstart.
- Check version strings and feature mentions against `docs/STATUS.md` — the parity gate
  in `citevahti-release` lists what each surface actually has.
- Pass the finished doc through `citevahti-claims` (install docs make product claims too).

## Hard rules

- **NEVER document a command you haven't run** against the current release.
- **NEVER paraphrase the safety framing** — reuse the canonical paragraph.
- **NEVER promise auto-update on any channel.**
- **NEVER fork the troubleshooting table** — one table, linked everywhere.
