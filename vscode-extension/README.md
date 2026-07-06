# CiteVahti — VS Code extension

*A product of **Vahtian**.* The inline citation-integrity surface (ADR-0002): your
manuscript is the screen, each claim is a unit test. Run **CiteVahti: Verify
claims** and every claim in the open document is highlighted by its 4-state
result, with a side report.

| Code | State | Highlight |
|---|---|---|
| `[oo]` | Accepted | amber |
| `[o ]` | Needs support | teal |
| `[r ]` | Review needed | violet |
| `[d ]` | Decision recorded | rose |

No green, no red — citation support is a research instrument, not an automated
judge (see `docs/design/tokens.css`).

## How it works
This extension is a **thin client** over the CiteVahti CLI. The command
`citevahti claim-report --json` produces the 4-state report (the same engine that
powers the agent's `verify_claims` tool); the extension decorates matching claim
spans in the active editor and renders the report in a webview. Clicking a report
row reveals the claim in the document. All judgments, writes, and the audit trail
live in CiteVahti — the extension never writes to Zotero itself.

## Setup
1. Install CiteVahti (a venv is recommended):
   ```bash
   python -m venv .venv && source .venv/bin/activate && pip install -e /path/to/Citevahti
   ```
2. In VS Code settings, point `citevahti.cliPath` at that `citevahti` binary (the
   legacy `citevahti` command also works), and set `citevahti.root` to the project
   containing `.citevahti/` (defaults to the workspace folder).
3. Build the extension:
   ```bash
   cd vscode-extension && npm install && npm run compile
   ```
   Then press **F5** to launch an Extension Development Host, open a manuscript,
   and run **CiteVahti: Check claims** (Command Palette).

## The review loop (interactive)
Expand a claim to see its candidate evidence cards. Each card shows the paper, the
**human** support rating, and the **AI** rating (*hidden until you rate* — blinding
is real), and the recorded decision. Focus a candidate and press a fit-code, or
click the buttons:

| Key | Action | Decision recorded |
|---|---|---|
| `o` `o` | Accept | `accept` (→ Accepted) |
| `o` | Caution | `accepted_with_caution` |
| `r` | Review | `needs_second_review` |
| `d` | Reject | `reject` |

The extension prompts for a reason and runs `citevahti claim-decide` — **the human
decides; CiteVahti records, audits, and can undo.** The mission invariant still
holds (you cannot accept a non-supporting paper; you cannot finalize on an
unresolved discordance) — the CLI enforces it and the extension surfaces the
message. This is a *human* surface (it drives the human CLI commands); the
constrained agent surface (`docs/AGENT.md`) is for AI agents.

## Adding a verified reference to Zotero (staged, undoable)
On an accepted candidate, **✓ Add to Zotero** runs the guarded write:
1. **Preview** (`claim-commit --json`, dry-run) — you see the proposed item,
   dedupe status, and any warnings in a confirm dialog. Nothing is written yet.
2. **Commit** — on confirm, the item is created (in `citevahti.collectionKey` if
   set) through a decision-gated transaction bound to the preview's confirm token.
3. **Undo** — the success notification offers *Undo*, which deletes only what the
   transaction created (version-guarded). If dedupe couldn't be verified, you get
   an explicit *Override and add* choice — never a silent duplicate.

## Status
Interactive: report + inline decorations + the `oo/o/r/d` decision loop + the
staged, undoable Zotero write + revision diffs from the card. Revision acceptance
applies a visible `WorkspaceEdit` and then records the audited claim revision.
