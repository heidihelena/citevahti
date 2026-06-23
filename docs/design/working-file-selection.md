# Working-file selection — design note

Companion to [ADR-0007](../adr/0007-local-web-app-and-http-surface.md) (local web
app + HTTP surface) and [ADR-0002](../adr/0002-ui-delivery-and-review-layer.md)
(UI delivery / review layer). This note captures *why choosing what to work on
feels hard today* and four ideas to make it easy. It is a problem statement +
options, not yet an accepted decision.

## The problem

Starting work in CiteVahti — "choosing the working file" — feels harder than it
should. The instinct is to blame the picker UI, but the friction survives even
though the UI is already reasonable. The real cause is a **mismatch of units**:

- **CiteVahti's unit of work is a folder + a hidden ledger.** You bind a
  *manuscripts folder*; the `.citevahti/` ledger is created at the folder root
  (`state/store.py` — `STATE_DIRNAME = ".citevahti"`); a fresh folder reports
  *"no ledger yet → run `citevahti init`"* (`panel/server.py`, the
  `not_initialized` message; `cli.py` `init`).
- **The researcher's unit of work is a manuscript** — *this paper* — not a
  folder and not a ledger.

So three things compete to be "the working file":

1. the **folder** you pick (the root that holds the ledger),
2. the **manuscript** (`.md`) that lives *inside* it,
3. the **ledger** (`.citevahti/`) that records the work, at the folder root.

The relationship is many-to-one and mostly invisible, so "I want to work on
paper X" becomes "which *folder* is paper X in, and does it have a ledger yet?"
That indirection — plus a separate `init` gate (choose ≠ ready) — is the friction.

It is compounded by **three surfaces resolving the root differently**: the MCP
server takes `--root` from client config, VS Code uses the workspace folder, and
the panel uses a filesystem picker with a remembered last-root. Each works on its
own, but "what am I working on" is defined per-surface, so it feels slippery.

### What is already good (do not rebuild)

- **Last-root is remembered** — `prefs.remember_root()` / `recall_root()`; the
  panel defaults to the last-used root and falls back to it when pointed at an
  empty folder (`panel/server.py`, `cli.py`).
- **A folder picker exists** — a loopback filesystem browser that counts `.md`
  files so the user can recognise "the folder with 3 manuscripts" without typing
  a path (`panel/server.py`).

**Verdict:** roughly 70% model/architecture, 30% UX. The fix is to make the
*manuscript* the thing you open, not the folder.

## Four ideas to make it easy

### 1. Manuscript as the first-class unit, with init-on-open
Let the user **open a manuscript** (`paper.md` / `.docx`) directly; CiteVahti
locates or *creates* its ledger automatically — no separate `citevahti init`
step. "Open this document" replaces "choose folder → init → bind manuscript".
- **Why:** matches the user's mental model exactly; removes the *choose ≠ ready*
  gate.
- **Effort:** medium. Keep `.citevahti/` as the store; change the *entry* from
  folder-first to document-first, with init folded into open.
- **Trade-off:** must decide where a per-document ledger lives (see idea 2) and
  keep `init` available for power users / CI.

### 2. A single, openable project manifest
Introduce one portable artifact — e.g. `<name>.citevahti` (or `citevahti.json`)
— that **binds the manuscript, its ledger, and config** into one file you open
like a `.docx`.
- **Why:** gives "the working file" a real, nameable, double-clickable identity;
  makes a project portable (move/copy/share one thing); makes recents and
  surface-handoff trivial because every surface opens the *same* artifact.
- **Effort:** larger — a manifest schema + migration from today's folder-rooted
  ledger.
- **Trade-off:** a second on-disk concept alongside `.citevahti/`; needs a clear
  rule for manifest ↔ ledger location (manifest can simply point at the ledger).

### 3. Recent *manuscripts*, not recent folders
Reuse the existing `remember_root` / `recall_root` machinery but key recents to
**documents**, and show a "Recent manuscripts" list on launch (panel first-run
and the VS Code/MCP entry hints).
- **Why:** the fastest relief for the daily case — reopen the paper you were on
  in one click, no filesystem reasoning. Low risk; builds on what exists.
- **Effort:** low.
- **Trade-off:** until ideas 1–2 land, a "recent manuscript" still resolves to a
  (folder, file) pair under the hood — acceptable as a stepping stone.

### 4. One shared working-file resolver across all surfaces
Define a single resolver that every surface (MCP `--root`, VS Code workspace,
panel picker) calls to answer "what is the current working file/ledger," with one
consistent precedence (explicit arg → manifest → recent → prompt).
- **Why:** removes the per-surface inconsistency so the answer to "what am I
  working on" is identical in Claude Desktop, VS Code, and the panel.
- **Effort:** medium; mostly consolidation of logic that already exists in three
  places.
- **Trade-off:** touches all three entry points at once — sequence it after the
  unit model (1/2) is settled so the resolver targets the right artifact.

## Recommendation (sequencing, not commitment)

1. **Ship idea 3 first** (recent manuscripts) — biggest daily relief, lowest risk,
   reuses existing prefs.
2. **Then idea 1** (document-first open + init-on-open) — removes the core
   model mismatch and the `init` gate.
3. **Then idea 4** (one resolver) — make every surface agree, now that the unit
   is a document.
4. **Idea 2** (manifest) is the larger bet — adopt it if/when portability and
   sharing of a whole project become first-class needs; ideas 1+3+4 already make
   the everyday case feel like "open my paper."

Open question for a follow-up ADR: does a per-document ledger replace the
folder-rooted `.citevahti/`, or sit alongside it for multi-manuscript folders?
