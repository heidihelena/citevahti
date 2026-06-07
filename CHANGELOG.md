# Changelog

All notable changes to CiteVahti (a product of Vahtian; formerly developed as
ZotSynth). The project was built in reviewed steps, each on its own branch off the
previous one.

## Unreleased

Panel UX hardening (the "medium" findings from the external review):

- **feat(panel): stable error codes + plain remediation.** Every panel API error now
  returns `{error, code, message, remediation}` — a stable `code` for automation and
  one plain remediation sentence for humans (e.g. an uninitialised ledger → code
  `not_initialized`, "Run `citevahti init` …"). The UI appends the remediation to the
  message it shows. Replaces raw `type(e).__name__` + bare exception text.
- **feat(panel): uncertainty legend.** A header **“?”** opens a plain-language legend:
  what `[oo]/[o]/[r]/[d]/[··]` mean, what *unsupported / unverified / contradicts*
  mean, and that CiteVahti checks **citation support, not clinical truth**.
- **feat(panel): accessibility.** Header controls have `aria-label`s; the agent lane
  is an `aria-live="polite"` region; claim spans expose an accessible name with their
  state ("claim pending: …") and hide the cryptic `[··]` chip from screen readers; the
  legend is a labelled region with `aria-expanded` wiring.
- **feat(panel): write-target disclosure.** Before a Zotero write the card now states
  where it will land — *"This write targets: library &lt;id&gt; via Zotero Web API.
  Permission: item creation only."* — sourced from the capability report. The library
  id is an identifier, never a secret; `/api/health` carries a `write_target` summary
  (backend, availability, library, permissions) and a test asserts no key material leaks.
- **feat(panel): first-run paste-a-manuscript hand-off.** The empty state gains a
  paste-Markdown box: `POST /api/manuscripts/paste` saves the `.md` (basename-only,
  path-traversal-safe, refuses to clobber), binds its folder, and returns the exact
  MCP prompt to run next. Claim **extraction stays in the chat client** — the panel
  never calls an AI — so the box explicitly hands off rather than pretending to extract.
- **feat(panel): bounded manuscript-backup retention.** After each `.md` edit the
  backup folder `<root>/.citevahti/manuscript_backups` is pruned to the **10 most
  recent backups per manuscript**; older ones are deleted automatically once the new
  backup is safely written, and the newest valid backup is never removed. Configurable
  via `CITEVAHTI_BACKUP_RETENTION_COUNT` (default `10`; non-positive/invalid → `10`).

## 0.14.0 — Integrity surfaces in the panel: audit chain, Zotero evidence, lexical check (2026-06-07)

Follows 0.13.0 with three integrity-facing additions to the inline reviewer, plus a
crash fix. No engine safety-invariant changes; the blinded human-first protocol and
the previewed/undoable write gates are unchanged. **Tagged for external review.**
588 offline tests.

- **feat(panel): audit-chain "verified ✓" indicator.** `GET /api/audit/verify`
  recomputes the hash chain (`store.audit.verify()`) and reports `{intact, entries}`.
  A header badge shows **⛓ audit ✓ N** (intact) or **⛓ audit ⚠ tampered** (broken,
  clickable to re-verify), and the per-claim audit trail summary gains
  *"· chain verified ✓"*. Refreshes on boot/reload and after each decision/write. A
  test retroactively edits an audit entry and confirms the endpoint reports the chain
  broken — the indicator genuinely catches tampering.
- **feat(panel): the paper's Zotero highlights + full text, in the card.**
  `tools.zotero_evidence` locates the candidate's library item and returns its PDF
  **annotations** (`zot_annotations`) and an indexed **full-text** snippet
  (`zot_fulltext`); an on-demand "Show Zotero highlights & full text"
  (`POST /api/zotero/evidence`) renders them. Paper content, not an AI assessment, so
  it is blinding-safe to read while rating.
- **feat(panel): deterministic lexical check.** `tools.claim_lexical_check` reuses the
  engine's content-token overlap (`retrieval/text.py`, the same logic as `claim_check`)
  to report whether the claim's key terms appear in the candidate's abstract
  (coverage + present/missing terms). Surfaced **only after the human rates**
  (`POST /api/claim-check`), so it never biases the blind rating; never asserts truth.
- **fix(panel): no-candidate claims no longer crash the card.** `renderAgent` built
  its phase strings eagerly and dereferenced `cand.rating` even when a claim had no
  linked candidate; it is now null-safe.

  *Security / integrity fixes from the external review of this build:*
- **fix(security): adjudication now requires a real discordance.** `support_adjudicate`
  previously **fabricated** `comparison.status = "discordant"` and set an
  `adjudication.final_value` with no human rating, no AI rating, and no computed
  disagreement — which a decision could then accept. It now refuses unless a **locked
  human rating** and an **AI second rating** exist and the comparison was **computed
  discordant**; `decide()` additionally only treats an adjudicated value as resolved
  when it rests on a locked human rating (defense in depth). Regression tests cover
  the bare-rating and concordant/human-only cases.
- **fix(security): OAuth request-token secrets never touch disk.** The temporary
  `oauth_token_secret` was written to `.citevahti/panel.json`; it is now held in the
  panel process only, single-use, with a 10-minute TTL — restoring the "panel JSON
  has no secrets" boundary.
- **fix(panel): document-edit commits are bound to the previewed contents.** A
  preview now records the source hash; `commit-edit` refuses (HTTP 409) if the `.md`
  changed since the preview, so a stale preview can't overwrite an intervening edit.
- **fix(ext): VS Code manuscript revisions get a durable backup + revert.** Accepting
  a revision now snapshots the file to `.citevahti/manuscript_backups` before the edit
  and adds a **"CiteVahti: Revert manuscript edit"** command — the extension's own
  safety, independent of the panel (not every user runs it).
- **chore(version/dist): 0.14.0 across the CLI and the VS Code extension**, `.vsix`
  rebuilt (the extension is version-aligned).

## 0.13.0 — The inline reviewer becomes the (self-sufficient) default panel (2026-06-07)

The loopback panel is rebuilt as the **inline manuscript reviewer** and promoted to
the default surface: your claims are highlighted in place in the manuscript, and an
action-first card walks one obvious next step at a time (**Rate → Reveal → Decide →
Write**). It is now **self-sufficient** — you can find evidence, rate, decide, write
to Zotero, and revise the manuscript without leaving for the chat. The blinded
human-first protocol is unchanged (the AI second rating still comes from your chat
client over MCP; the panel never produces it). All writes — Zotero **and** the
manuscript `.md` — stay previewed, confirmed, and undoable; connect secrets go to the
OS keychain and never return to the browser; `agent.TOOLS` is untouched (no new agent
capability). 582 offline tests.

- **feat(panel): the inline reviewer is the default surface.** New
  `panel/manuscript.py` binds a manuscripts folder, resolves each claim onto the real
  prose (whitespace-tolerant span mapping), and falls back to a reconstructed
  claim-text document so it is never blank. New endpoints `GET /api/manuscripts`,
  `GET /api/manuscript/{id}`, `POST /api/manuscripts/bind`. Document order drives the
  `j`/`k` navigation, the progress rail, and auto-advance.
- **feat(panel): first-run onboarding ends the empty-ledger trap.** `citevahti-panel`
  / `start` now default to `$CITEVAHTI_ROOT`, the cwd ledger, or the **last-used
  root** (`panel/prefs.py`) instead of an empty `~/.citevahti`. An empty ledger shows
  a first-run screen that discovers other ledgers (with claim counts) and offers a
  one-click switch (`GET /api/ledgers`, `POST /api/root`, `GET /api/context`).
- **feat(panel): connect Zotero & PubMed in-panel.** Header chips + inline forms;
  Zotero via paste-a-key **or** a one-click **OAuth 1.0a** handshake (new
  `zotero/oauth.py`, `POST /api/connect/zotero/oauth/start` + loopback
  `/oauth/zotero/callback`; client key/secret from the env, configurable callback).
  Both converge on the same validated, keychain-stored, write-enabled state.
- **feat(panel): find evidence from four sources, then link.** `POST /api/search`
  over **PubMed**, **OpenAlex** (`openalex.py`), **Semantic Scholar** (`semscholar.py`)
  and your **Zotero library**; `POST /api/link` attaches a result as a candidate —
  no chat required. OpenAlex/Semantic Scholar are the API-backed answer to Google
  Scholar (which has no usable API).
- **feat(panel): automatic DOI backfill.** Missing DOIs are resolved from PMIDs via
  NCBI **at link time**; a **Resolve DOIs** action backfills existing candidates
  (NCBI PMID→DOI, plus strict CrossRef title→DOI in `crossref.py` for identifier-less
  ones). PMID→DOI and exact-title matching only — a wrong DOI is worse than none.
- **feat(panel): retraction scan.** A **⚠ Retractions** action flags candidates whose
  DOI/PMID is retracted (OpenAlex `is_retracted`) with a **RETRACTED** card tag —
  CiteVahti's integrity flagship, now real. New `retracted` field on candidates.
- **feat(panel): open the reference PDF in Zotero.** An **Open in Zotero** action
  locates the library item by DOI (`POST /api/zotero/locate`) and deep-links its PDF
  (`zotero://open-pdf/...`).
- **feat(panel): add claims & author revisions without the chat.** A **＋ Claim**
  form (prefilled from a manuscript selection) creates claims (`POST /api/claims`); a
  *Needs review* verdict gives an editable wording box that writes the revision to
  your `.md` (and *Reject* strikes the claim) behind a preview → confirm → undo gate
  with a file backup.
- **feat(panel): library maintenance & at-a-glance tags.** **Re-check library**
  re-runs Zotero dedupe; candidate cards show **✓ in Zotero / DOI ✓ / no DOI /
  ⚠ RETRACTED** tags.
- **feat(panel): per-claim audit trail.** `GET /api/claims/{id}/history` assembles a
  timeline of the claim's decisions and Zotero write transactions (timestamp · verdict
  · who · agreement · reason; writes show undone status) — the auditable
  claim-evidence trail, in the card.
- **fix(panel): the decision loop now visibly changes.** A claim is "decided" for any
  non-pending state (`verified`/`review_needed`/`decision_recorded`), not only
  `decision_recorded`; an Accept/Revise verdict now colours the manuscript span,
  advances the progress rail, and auto-advances. Also fixed: `j`/`k` and auto-advance
  follow **document** order (not ledger order), and the candidate stays selected across
  a same-claim refresh.
- **fix(panel): connect feedback, request handling, caching.** The Zotero connect
  control prompts for a key (it no longer silently no-ops); a required-reason error
  flags the field in place instead of off-screen; the server forces `Connection:
  close` (fixing a keep-alive wedge) and sends `no-cache` for static assets so a
  refresh always loads the latest UI.
- **design(panel): calmer, document-first colours.** Near black-and-white reading
  area, lilac decision panels, and a clear soft-lilac claim highlight (`--zs-mark`) so
  claims stand out in the prose without colouring the whole page.
- **chore(version): 0.13.0 across the CLI and the VS Code extension** (the extension
  is version-aligned; no extension code changes this release).

## 0.12.0 — Rate-first in the VS Code card (2026-06-06)

The VS Code inline card adopts the same **rate-first** rule the side panel already
enforces: you rate the support before you can decide. No engine or safety-invariant
changes; the Python core is unchanged from 0.11.1 and republished only to keep one
version number across the CLI and the extension. 544 offline tests.

- **feat(ext): rate-first gating in the VS Code inline card.** The card no longer
  lets you decide before you rate. A candidate now shows the blind support-rating
  buttons first (keys **1–6** → `directly_supports` … `unclear`); the
  Accept / Caution / Review / Reject verdict (and its `o/o/r/d` keys) stay locked
  until a human support rating is committed — the same rate-first rule the side
  panel enforces. Recording the rating starts + locks it (`claim-support-start`
  then `claim-support-commit-human`) and unblinds the AI's second opinion. Closes
  the last one-click-decides gap (RECAP #2).

## 0.11.1 — `start` hardening + version/doc alignment (2026-06-06)

Post-release fixes from the external review of 0.11.0. No engine or
safety-invariant changes; 544 offline tests.

- **fix(start): don't trust a busy port.** When the panel port is occupied,
  `start` now probes `/api/health` (`is_citevahti_panel`): if it's genuinely a
  CiteVahti panel it reuses it and opens the browser there; if it's a foreign
  occupant it **fails loudly** (exit 2) instead of pretending a rating surface
  exists.
- **fix(start): enforce loopback inside `start()`.** The loopback invariant now
  lives in `start()` too (refuses any non-loopback `host` with exit 2), not only
  in `citevahti-panel` — defense in depth.
- **fix(version): align the VS Code extension to 0.11.0/0.11.1.** `package.json`
  and `package-lock.json` were still 0.10.0, so packaging produced a stale
  `0.10.0.vsix` and made the extension look un-updated.
- **docs:** README/QUICKSTART test count (→544) and `.vsix` name (→0.11.x)
  refreshed; QUICKSTART now installs from PyPI (`pip install citevahti`), not
  "from source; PyPI coming"; chat docs lead with the canonical `run_claim_tests`
  prompt (`review_manuscript` noted as the deprecated alias).

## 0.11.0 — One command: `citevahti start` (2026-06-06)

The biggest friction cut for ordinary researchers: collapse the three-step setup
(register the MCP server, launch the panel, open a browser) into a single command
that *also* serves as the one line in a chat client's MCP config. No engine or
safety-invariant changes. 541 offline tests.

- **feat(start): `citevahti start` — launch the whole v1 workspace at once.** Brings
  up the loopback side panel + browser in a background thread, prints plain
  next-step prompts ("Open Zotero", "Choose a manuscript"), then serves the
  constrained MCP tools over stdio in the foreground. Put it straight in the client
  config: `"command": "citevahti", "args": ["start", "--root", "…"]`.
  - **stdout stays the MCP protocol channel** — every human-facing line is written
    to stderr, so the stdio stream the chat client reads is never corrupted.
  - **Loopback only** — `start` binds `127.0.0.1`; the non-loopback escape hatch
    stays in `citevahti-panel`, not here.
  - **Graceful degradation** — if the `mcp` extra isn't installed it keeps the
    panel up instead of crashing; if the panel port is busy it assumes one is
    already open and still serves MCP.
  - Flags: `--port` (default 8765), `--no-browser`.
- **refactor(cli): share `preflight_snapshot`.** `citevahti preflight` and `start`
  now read readiness from one function (`citevahti.start.preflight_snapshot`),
  removing the duplicated probe/claims/capability logic.
- Docs: `docs/CHAT_AND_PANEL.md` §2 documents the one-command path; the manual
  three-step path is kept as the equivalent fallback.

## 0.10.0 — The claim-test frame + 0.9.0 review fixes (2026-06-06)

Adopt the **"the manuscript is the code; each claim is a test"** product frame, and
fold in the fixes from the external 0.9.0 review. No engine or safety-invariant
changes — the surfaces are reframed and hardened. 534 offline tests.

- **fix(panel): address the 0.9.0 review findings.**
  - Connection dot no longer shows "broken" when connected — it now recognizes the
    real capability statuses (`connected`/`configured`), not a non-existent
    `available`/`ok`.
  - Switching claim or candidate resets the pending decision + approval token, so a
    write preview/commit can never run against a stale decision.
  - A decision reason is now required (it is audited) — no silent "(no reason
    given)".
  - Wording: "Accept as supporting reference" (accepting is not the same as writing
    to Zotero).
- **fix(panel): enforce loopback.** `citevahti-panel` refuses to bind a
  non-loopback address unless `--allow-nonloopback` is passed (with a warning) —
  the panel has no auth and renders manuscript claims/evidence.
- **fix(ext): refresh the stale `package-lock.json` version (0.7.0 → 0.9.0).**
- _Known follow-up:_ the VS Code inliner still shows decision buttons before a
  human support rating (the new side panel enforces rate-first). Tracked separately.

- **feat(frame): "the manuscript is the code; each claim is a test."** Adopt the
  claim-test product frame across the prompt, vocabulary, report, and docs.
  - The canonical MCP prompt is now **`run_claim_tests`** (`review_manuscript` kept
    as a deprecated alias from 0.9.0). It instructs the agent to walk the manuscript
    claim by claim, resolve existing citations, flag broken/hallucinated references,
    distinguish *paper existence from claim support*, weigh PICO/meaning, take the
    **human rating first** (AI blinded until then), classify each claim
    `[oo]`/`[o]`/`[r]`/`[d]`, preview→confirm→undo Zotero writes, and emit a report.
  - **Stable finding labels** (`src/citevahti/findings.py`): `support_direct`,
    `related_but_insufficient`, `reference_broken`, `reference_hallucinated`,
    `reference_real_but_wrong`, `*_mismatch`, `overclaim`, `needs_full_text`,
    `zotero_*`, … — a cross-surface vocabulary, pinned by tests.
  - **Plain-language state labels** (`STATE_LABEL`): verified / needs support /
    review needed / decided.
  - **Claim Test Report** formatter (`report.render_test_report`) + `citevahti
    report` CLI (and `claim-report --format test`): a state-count summary plus
    per-claim finding/rating/decision, blinding preserved.
  - Docs: `docs/workflows/run-unit-tests-on-a-manuscript.md`; README reframed to
    "CiteVahti runs unit tests on manuscript claims" (VS Code = one adapter, PyPI =
    one install path).

## 0.9.0 — Chat + side-panel surfaces (2026-06-06)

The primary researcher workflow moves off the IDE: you drive the blinded review
from a **conversation** and a **localhost side panel**, while VS Code becomes one
adapter. The MCP spine, the engine, and every safety invariant are unchanged and
reused — the two new surfaces only render and drive existing engine state. 524
offline tests. See [ADR-0007](docs/adr/0007-local-web-app-and-http-surface.md).

- **feat(agent): a `review_manuscript` MCP prompt.** A user-controlled MCP prompt
  (`src/citevahti/agent/prompts.py`) registered on the existing FastMCP server
  choreographs a blinded, sentence-by-sentence review: the human rates **first** in
  the side panel, the AI rating is submitted **after**, and every Zotero write is
  previewed before commit. The tool surface is unchanged.
- **feat(panel): a loopback side panel + thin HTTP API.** `citevahti-panel`
  (`src/citevahti/panel/`) serves the inline evidence card on `127.0.0.1` as the
  **blind human decision surface**. Every endpoint maps onto existing engine/agent
  functions; the guarded write reuses the token-gated wrappers (preview → commit →
  undo). No raw Zotero write, no agent final decision, no credential exposure, no
  telemetry, no external bind. A read endpoint never reveals the AI rating before a
  human rating exists.
- **feat(panel): evidence excerpt + PICO fit-checks.** The candidate now snapshots
  the paper's own `abstract` (read before rating; blinding-safe), and the panel
  surfaces the read-only report's per-candidate PICO fit, citation-fit score, and
  blinded `ai_support` — fit/excerpt come only from the committed human rating.
- **feat(review): one-command Start review with a setup checklist + humane labels**
  (carried in on this branch).
- **fix(state): inter-process lock on the audit log.** The MCP server and the panel
  write the same `.citevahti/` ledger; `AuditLog.append` now holds a POSIX `flock`
  so concurrent appends cannot corrupt the hash chain.
- **chore(brand): marketplace icon from the real webpage logo.**
- **docs:** `docs/CHAT_AND_PANEL.md` (the v1 chat + panel setup) and `docs/AGENT.md`
  updated; ADR-0007 records the two co-primary surfaces (the full web editor +
  Streamable-HTTP transport are the **paid hosted tier**, ADR-0003 — not this one).

## 0.8.0 — Full rename to CiteVahti + a richer inline review card (2026-06-05)

The product fully sheds the `zotsynth` name (ADR-0006), the inline evidence card
gains the data a researcher actually weighs, and "Change reference" becomes a real
search-and-link flow. Folds in the post-0.7.0 work (rebrand, guided Zotero
connect, safety hardening, QUICKSTART). 502 offline tests.

- **refactor(rename): full rename `zotsynth` → `citevahti` (ADR-0006).** The
  importable package (`src/citevahti/`), the CLI (only `citevahti` /
  `citevahti-mcp` now), the OS-keychain service (`CiteVahti`), the env vars
  (`CITEVAHTI_*`), and the on-disk state dir (`.citevahti/`) all move to the brand
  name; `ZotSynthStore` → `CiteVahtiStore`. **Supersedes ADR-0004 §2.3a/§6** (the
  stable-alias decision): pre-1.0, single-user, no installed base, so the
  disruptive rename is free now and won't be later. History (ADRs, this changelog,
  release notes) keeps the old name as the record.
- **feat(report): PICO fit + excerpt on the inline evidence card.** The report now
  surfaces — **only from the committed human rating, never the blinded AI** — each
  candidate's PICO + claim fit subscores, a citation-fit score (`n/8`,
  Strong/Moderate/Weak), and the supporting excerpt, rendered as fit-check chips on
  the VS Code card. Mirrors the existing `ai_support` blinding so the card can't
  leak the AI assessment. +1 test.
- **feat(change-ref): a real "Change reference" flow.** New `--json` output on
  `literature-search` (batch id + staged hits) and `claim-link-candidates`
  (linked/skipped/total); the VS Code **"⇄ Change reference…"** action searches
  PubMed (verbatim query), lets you pick results, and links them as new candidates.
  Swapping among already-linked candidates is afforded directly on the card. Links
  only — no rating, decision, or Zotero write. +2 tests.
- **docs(readme): "Try it" + "What to test".** A followable 4-step inline-review
  walk-through and a what-to-test block (offline suite + extension build + a manual
  acceptance checklist); fixes the rename artifact in the header note and the test
  count (→ 502).
- **fix(safety): stress-test findings — preview-first CLI write + honest Zotero scope.**
  - **Sev-4 (the important one):** `claim-commit --commit` no longer one-call writes.
    Without `--confirm-token` it now **shows the preview and requires explicit
    confirmation** (interactive `y/N`); non-interactive callers (scripts/agents)
    must replay the token, and `--json` returns `preview_required /
    missing_confirm_token` — so nothing is ever written unseen. `claim-decide`'s
    hint reworded to "review+write (shows a preview and asks)".
  - **Sev-3:** `connect-zotero` now reports **personal-library write vs group-library
    access** honestly (no false confidence), adds `--groups none|read|write` (and a
    VS Code "Include shared/group" choice) to pre-select shared-library scope.
  - **Sev-2:** `decision-list` now prints each `decision_id` (+ the `claim-commit`
    command) so the write id is recoverable; PyPI build verified end-to-end and the
    recipe captured in `docs/RELEASING.md`.
  - **Sev-1:** README test count corrected (→ 499).
- **docs: `QUICKSTART.md` — zero to first verified citation (~10 min).** Install →
  `connect-zotero` → add a claim → PubMed search → rate → decide → guarded write →
  report, with both the VS Code review loop and the full CLI path. Linked from the
  README. Also: `claim-decide` now prints the `decision_id` and the exact
  `claim-commit` command (removes a `decision-list` lookup on the CLI write path).
- **feat(zotero): guided one-paste connection — no hand-crafted API keys (ADR-0005).**
  A spike confirmed Zotero's local API is read-only and the connector write path is
  fragile/undocumented, and that OAuth needs a callback server (→ a hosted feature).
  So the beta connects keyless reads + a **one-paste key** for writes:
  `citevahti connect-zotero` (and the VS Code **“Connect Zotero”** command) opens
  Zotero's new-key page **pre-filled** (name + `write_access=1`), takes the pasted
  key, validates it against the Web API, **learns the userID automatically**, stores
  the key in the **OS keychain** (never config/argv/logs — the extension passes it
  by env), and enables the guarded `web_api` backend. Read-only/invalid keys are
  refused; write-back stays decision-gated, previewed, and undoable. New
  `zotero.ZoteroConnectService`, `tools.connect_zotero` / `zotero_new_key_url`,
  `connect-zotero` CLI, and the `citevahti.connectZotero` command. +9 tests.
- **chore(brand): rebrand the product to CiteVahti (a product of Vahtian).** The
  distribution is now `citevahti`; the CLI is `citevahti` / `citevahti-mcp`; the VS
  Code extension is `vahtian.citevahti` (command `CiteVahti: Verify claims`, config
  namespace `citevahti.*`); README, NOTICE, and forward-facing docs are rebranded.
  **Kept as stable aliases so nothing breaks:** the Python import path `zotsynth`,
  the `zotsynth` / `zotsynth-mcp` CLI commands, the `ZotSynth` OS-keychain service
  (stored secrets survive), and the `.zotsynth/` state directory. See
  [ADR-0004](docs/adr/0004-brand-ip-and-entity.md). Also fixed a stale
  `__version__` (0.6.0 → 0.7.0).
- **docs: add `CONTRIBUTING.md`** — DCO sign-off gate + the open-core ground rules,
  so external contributions come in cleanly and the open-core boundary holds.

## 0.7.0 — Manuscript surfaces: interactive review, editor report, revision diff (2026-06-04)

The manuscript becomes the workspace. Three surfaces over the one ledger
(claim → candidate → blinded rating → decision → guarded write): an **inline
VS Code review loop**, an **editor-mode Markdown report** for supervisors/editors,
and an **agent-proposes / human-accepts revision diff**. Hardened across two
headless-reviewer passes and a **live VS Code F5 pass** (disposable workspace +
fake Zotero Web API): the decision loop, preview→commit collection/token binding,
and undo all verified live; the revision-accept path verified live after the
manuscript-location fix below.

- **fix(F5): bugs found and fixed during the live extension run.**
  - **Undo retry no longer carries a stale `undo_unavailable`.** A successful undo
    after a prior failed one now clears `error_code`/`remediation`
    ([writeback/transaction.py]); regression test
    `test_successful_retry_clears_prior_undo_failure_fields`.
  - **Nonce-based webview CSP.** The panel sets
    `default-src 'none'; style-src/script-src 'nonce-…'` and stamps the inline
    `<style>`/`<script>` with the nonce — no missing-CSP warning, no inline-script
    escape hatch.
  - **Revision accept no longer depends on the active editor.** The pending rewrite
    carries `manuscript_location` to the webview; accept opens the manuscript from
    that location if needed, then applies the edit.
- **fix(safety): headless-reviewer hardening of the write + revision paths.**
  - The card's **preview→commit is now tightly bound**: the preview sends
    `--collection-key` and the commit replays the preview's **`confirm_token`**
    (`--confirm-token`) — no commit without a confirmable preview, and the target
    collection is shown in the confirm modal.
  - **`oo` no longer double-records.** A single-`o` keypress is held on a short
    timer so a fast `o o` resolves to one `accept`, never `accepted_with_caution`
    then `accept`.
  - **Revision accept can no longer diverge** manuscript text from ZotSynth state:
    single-span selection / duplicate guard, rollback of the manuscript edit if the
    CLI fails, and a **stale-diff guard** — `claim-accept-revision --expected-text`
    (and `accept_revision(expected_text=…)`) refuses to apply if the pending rewrite
    changed since it was previewed.
- **feat(revision): the revision-diff loop — propose → review the diff → accept/reject.**
  A claim can carry a *pending rewrite*. An agent may **propose** one
  (`propose_revision`, flagged `ai` with a pinned model) but can **never apply** it
  (`accept_revision` is a forbidden agent capability); only a human accepts. The
  inline card renders the pending rewrite as a **−was / +now diff** with *Accept
  revision* / *Keep original*, plus *✎ Revise wording…* for a human-authored
  rewrite. **Accept applies a visible `WorkspaceEdit`** to the manuscript text and
  then updates the stored claim — the claim text is **never silently edited**, and
  the change is audited with the before/after. New CLI: `claim-propose-revision`,
  `claim-accept-revision`, `claim-reject-revision`; the report row + editor-mode
  Markdown surface the pending rewrite.
- **feat(vscode): the interactive `oo/o/r/d` decision loop.** Expanding a claim
  shows its candidate evidence cards (paper, human rating, AI rating *blinded
  until the human rates*, recorded decision). Focus a candidate and press a
  fit-code (or click): `oo`→accept · `o`→accepted_with_caution · `r`→
  needs_second_review · `d`→reject. The extension prompts for a reason and runs
  `claim-decide` (the human decides; ZotSynth records/audits/undoes), then
  refreshes the report + decorations. The mission invariant is enforced by the
  CLI and surfaced in the UI.
- **feat(report): evidence carries `rating_id` + blinded human/AI support** so the
  card has what it needs to act (the AI value is `"hidden"` until the human rates).
- **feat(report): editor-mode Markdown report (`--format md`).** A shareable
  **Citation-Integrity Report** for supervisors / journal editors / methodologists
  — read-only, claim-by-claim with state, evidence, ratings, and decisions, an
  "attention needed" section, and a non-overclaim footer. `claim-report --format
  text|md|json --output <file>`; new `report.render_markdown`. No Zotero write.
- **feat(vscode): staged, undoable Zotero write from the card.** "✓ Add to Zotero"
  on an accepted candidate **previews** (`claim-commit --json` dry-run; you confirm
  the item + dedupe status), **commits** through the decision-gated transaction,
  and offers **Undo** (deletes only what it created). `dedupe_unverified` surfaces
  an explicit *Override and add* — never a silent duplicate. Adds `--json` to
  `claim-commit` / `txn-undo`, `decision_id` to the report evidence, and a
  `zotsynth.collectionKey` setting.

## 0.6.0 — citation-integrity report + VS Code surface + Apache-2.0

Tag: `v0.6.0`. The 4-state report (the VS Code / editor / agent data) and the VS Code
extension first cut; relicensed to Apache-2.0.

- **feat(report): the 4-state citation-integrity report.** Treats the manuscript
  like code — each claim is a unit test whose state is *derived* (read-only) from
  the ledger: `[oo] verified` (accepted supporting evidence), `[o ] needs_support`
  (no accepted evidence yet), `[r ] review_needed` (unresolved discordance / a
  2nd-review decision), `[d ] decision_recorded` (all candidates settled, none
  accepted). New `schemas/report.py`, `report/ClaimReportService`,
  `tools.claim_report`, and a CI-style `claim-report` CLI (`--json` for tooling;
  exits non-zero when claims still need attention).
- **feat(agent): `verify_claims`** — the read-only report added to the constrained
  agent surface so an agent can run the citation tests (still no write power).
- **feat(vscode): VS Code extension (first cut).** `vscode-extension/` — a thin
  client over `claim-report --json` that highlights each claim in the open
  manuscript by its 4-state result (amber/teal/violet/rose, no green/red) and
  shows a side report. The interactive `oo/o/r/d` keystroke flow + evidence-card
  popover (prototyped in `mockups/zotsynth-inline/`) wire to the MCP tools next.

## 0.5.0 — constrained agent (MCP) surface

Tag: `v0.5.0`. ZotSynth is now safely callable by AI agents (MCP): capability without power.

- **feat(agent): the constrained agent tool surface.** Exposes ZotSynth to AI
  agents (Codex/Claude Code) as a small, fixed set of safe verbs — *capability
  without power*. `pubmed_search`, `propose_claim`, `link_candidates`,
  `start_support_rating`, `submit_ai_support_rating` (recorded **blind**, value
  not echoed), `preview_write` → `commit_write(approval_token)`, `undo`,
  `get_provenance` (AI rating **blinded until the human rates**), `status`. An
  agent can NEVER reach a raw Zotero write, a one-call commit, the human's rating,
  the final decision, the AI rating before the human, or credentials — enforced by
  `agent/policy.py` (asserted at import + serve). New `agent/` package, a lazy
  `mcp-serve` MCP server (`zotsynth-mcp`, optional `[mcp]` extra), `agent-tools`
  CLI, `ClaimSupportEngine.submit_ai_rating`, and `docs/AGENT.md`. +9 tests.

## 0.4.1 — beta hardening (second stress test)

Tag: `v0.4.1`. Closes the agent-write-boundary + dedupe-unverified findings.

- **fix(writeback): agent-write boundary — a confirmed validated write requires a
  prior preview's approval token.** `commit_for_decision(dry_run=False)` /
  `tools.commit_decision` now refuse (`missing_confirm_token`) unless given a
  token from a prior dry-run preview, so an agent cannot one-call write to Zotero
  without a user-visible preview/approval step. The CLI `claim-commit --commit`
  previews then commits (human one-command path); an explicit `--confirm-token`
  is also accepted.
- **fix(writeback): `dedupe_unverified` no longer proceeds silently.** When the
  write-target existence check is unavailable (Zotero search down), a validated
  write is **refused** (`dedupe_unverified`) rather than risking a duplicate;
  override with `allow_unverified_dedupe` / `--allow-unverified-dedupe`. Dry-run
  previews warn.
- **fix(writeback): block writes from `review_required` intake batches.** A batch
  flagged for review (malformed/translated PubMed query) is blocked from
  committing (`batch_review_required`) unless `--allow-review-required`.
- **fix(ui): mockup language + blinded validation.** The `d` state reads
  **Unsupported** (not "Delete"); actions are "Remove candidate from claim" /
  "Remove candidate + strike claim (diff)" with explicit diff/undo framing; the
  inline mock now hides the AI rating during blinded human validation (was
  leaking it).
- **fix(cli): `claim-commit --commit` returns non-zero on a non-committed write**
  (reviewer-contributed, with a regression test).

## 0.4.0 — validation warehouse + UI direction + duplicate-safety

**First public beta milestone.** Tag: `v0.4.0`. Completes the ADR-0001 §10 build
sequence (the de-identified validation warehouse, step 6), records the inline
review-layer UI direction (ADR-0002), and closes the stress-test duplicate-safety
blockers. 443 tests, fully offline. Beta scope: local-first, single-user,
PubMed-only; the hosted layer and the VS Code review-layer UI are the next phase.

### Inline review-layer UI (ADR-0002)
- **docs(design): ADR-0002 — the `[oo/o/r/d]` inline review layer.** Citation
  integrity lives *inside* the writing surface (a VS Code-style editor companion),
  not a separate dashboard. Four operational fit-codes over the ledger
  (`oo` supported→accept · `o` partly→accepted_with_caution · `r` revise→2nd
  review · `d` delete→reject), four distinct accessible status hues
  (amber/teal/violet/rose; lilac brand; no green/red), claim text never edited
  silently (inline diffs), and the `r`/`d` cards each expose their two real
  choices. Adds `docs/design/` (tokens, reference, logo) and runnable mockups
  (`mockups/zotsynth-inline` primary; `zotsynth-ui` dashboard demoted to legacy).

### Duplicate-safety hardening (stress-test Sev-4)

- **fix(writeback): cross-boundary duplicate protection.** Library dedupe checks
  the *local* Zotero API, so a paper created via the Web API but not yet synced
  locally looked "new" and could be duplicated. Backends gain
  `find_existing(pmid, doi)` (queries the **write target**); the validated
  `commit_for_decision` re-checks it and **refuses** with a `failed` /
  `duplicate_on_write_target` transaction (dry-run warns), and an uncheckable
  result degrades to "proceed" (never blocks a write because the check was down).
- **fix(writeback): `intake-push` hardening.** The generic staging push now
  enforces the same rules as the validated path — it skips `duplicate_in_run`
  records, records with **no PMID/DOI**, items already in the local library, and
  items already on the Web-API write target (was: staged all of them and minted a
  token).
- **fix(cli): clean errors for transaction/state failures.** `_safe` now catches
  `TransactionError` / `StateError` / `WriteUnavailable` (e.g. undoing an
  already-undone transaction) and prints a one-line message instead of a traceback.
- **feat(claims): `implementation` claim type** (implementation-science claims are
  first-class for guideline/QI users).
- **fix(writeback): committed `intake-push` records a transaction + undo.** The
  staging write now produces a `ZoteroTransaction` (`validated=False`) with an
  undo path, like the validated path. The CLI shows created keys / collection /
  transaction id (post-write verification).
- **fix(intake): `review_required` on malformed/translated queries.** PubMed
  warnings or a query re-translation flag the intake record and surface a
  prominent CLI "REVIEW REQUIRED" banner (Sev-3).
- **fix(cli): unsupported previews stop printing a blank `confirm_token`** — they
  say no confirmable write was produced and exit non-zero (Sev-2).
### Validation warehouse (ADR-0001 step 6)
- **feat(warehouse): de-identified validation warehouse (ADR-0001 step 6).** The
  reusable validation asset — but privacy-bounded. **Opt-in, default-off** (`config.validation_warehouse`).
  When enabled, a final decision becomes one append-only, de-identified
  `ValidationRecord`: `claim_type`, a one-way claim-text hash, the public PMID/DOI,
  the AI/human/final support ratings, PICO fit, and agreement. It stores **no**
  identity, manuscript text, Zotero keys, or project-internal ids. Claim text is a
  top-sensitivity tier kept only on a second opt-in (`include_claim_text`). Records
  are append-only (`validation/records.jsonl`); the warehouse is purgeable (consent
  withdrawal) and `auto_emit` lets labels emerge from the workflow. New
  `schemas/validation_record.py`, `warehouse.py`, config block, store CRUD
  (`validation.record` / `validation.purge` audit), and `warehouse-status/-emit/
  -export/-purge` CLI. Completes the ADR-0001 §10 build sequence.

## 0.3.0 — citation-integrity ledger (ADR-0001 steps 1–5) + capability foundation

Tag: `v0.3.0-citation-ledger`. Reorients ZotSynth around the **claim** (ADR-0001):
the ledger is `claim → candidate → blinded support rating → final decision →
decision-gated, undoable Zotero write`, every step hash-chain audited. Also folds
in the connection/capability hardening sprint. 421 tests, fully offline.

### Citation-integrity direction (ADR-0001)

- **docs(adr): ADR-0001 — ZotSynth is Citation Integrity Infrastructure.** The
  claim (not the paper) is the spine; the evidence-decision ledger is the asset;
  writes are decision-gated. Reconciles the manifesto against the current code;
  records four accepted decisions and a six-step local-first build sequence.
- **feat(claims): the claim entity (ADR-0001 step 1).** First-class,
  manuscript-anchored `Claim` (`claim_text`, controlled `claim_type`,
  `manuscript_location`, extraction provenance), persisted to
  `.zotsynth/claims/`, provenance-stamped and audited (`claim.write`).
  AI-extracted claims must name their model (mirrors the AI-needs-provenance
  rule). New `claims/` package, `schemas/claim.py`, `validators/claim.py`, store
  CRUD, and `claim-add` / `claim-list` CLI. Mutates no Zotero state, decides
  nothing — the spine only.
- **feat(claims): claim ↔ candidate linkage (ADR-0001 step 2).** Link staged
  intake hits to a claim as `ClaimPaperCandidate`s, preserving retrieval
  query/source/rank/why-found, deduped per claim by normalized PMID/DOI (never
  title-only). Persisted to `.zotsynth/candidates/<claim_id>.json`, audited
  (`candidate.link`). New `schemas/candidate.py`, `validators/candidate.py`,
  `CandidateService`, store CRUD, and `claim-link-candidates` / `candidate-list`
  CLI. Asserts no support, decides nothing, writes nothing to Zotero.
- **feat(claims): claim-support dual rating (ADR-0001 step 3).** The core asset
  dimension — *does this paper support **this claim**?* — distinct from study
  quality. A `ClaimSupportRating` keyed to `(claim_id, candidate_id)` with a
  controlled support vocabulary (`directly_supports … contradicts`/`unclear`) +
  PICO fit subscores (0/1/2). Rides on the same dual-rating invariants and
  **reuses** the proven value blocks (`AIProvenance`/`Comparison`/`Adjudication`/
  `Blinding`): human value locked, AI blind + advisory + never final, discordance
  needs human/panel adjudication, final never sourced from AI. New
  `schemas/claim_support.py`, `validators/claim_support.py`, `ClaimSupportEngine`
  + `ClaimSupportRater` seam (`FakeClaimSupportRater`), store CRUD with the
  human-lock guard, and the `claim-support-*` CLI family.
- **feat(claims): final decisions (ADR-0001 step 4).** The human-owned terminal
  judgment per (claim, candidate): `accept | reject | needs_second_review |
  accepted_with_caution`, recording the final support status it rests on, the
  human/AI agreement status, decider, and reason. **Mission invariant** (enforced):
  you cannot `accept`/`accepted_with_caution` a candidate whose final support
  status does not support the claim, and you cannot finalize accept/reject on an
  unresolved discordance (adjudicate first or record `needs_second_review`). New
  `schemas/decision.py`, `validators/decision.py`, `DecisionService`, store CRUD
  (`decision.final` audit), `claim-decide` / `decision-list` CLI. This is the
  object the decision-gated write (step 5) will require.
- **feat(writeback): decision-gated write transactions + undo (ADR-0001 step 5).**
  Promotes the one-use write token into a durable `ZoteroTransaction`
  (`previewed | committed | undone | failed`) with an `undo_snapshot`, enforcing
  the §6 invariant: a *validated* Zotero write exists only for a final `accept`/
  `accepted_with_caution` decision and always carries its chain (claim · candidate
  · decision · provenance · transaction · audit · undo). Refuses a candidate with
  no PMID/DOI (anti-fabrication); previews by default; degrades honestly to a
  `failed` transaction with no silent write. `undo` deletes **only** the keys the
  transaction created, version-guarded (`If-Unmodified-Since-Version`) so a user
  edit aborts the delete (HTTP 412) instead of clobbering it. New
  `schemas/transaction.py`, `validators/transaction.py`, `TransactionService`,
  backend `undo()` capability (+ `HttpClient.delete`), store CRUD
  (`zotero.transaction.*` audit), `claim-commit` / `txn-list` / `txn-show` /
  `txn-undo` CLI. Closes the stress-test's "no undo" gap.

### Connection & capability foundation

Hardening sprint driven by an external persona stress test. Builds a
truth-telling foundation and fixes four verified bugs (each a violation of
ZotSynth's own integrity invariants).

- **feat: `zotsynth status` — Connection & Capabilities (read-only).** Reports
  live Zotero/BBT connection + versions, PubMed email + secret *state* (source,
  never the value), and the configured write backend's **actual** supported vs
  unsupported operations + a permission summary. `capabilities.py` +
  `CapabilityStatusService`.
- **fix(credentials): keyring errors degrade gracefully.** A macOS
  `KeyringError(-50)` during NCBI-key lookup used to crash `literature_search`
  (`resolve_secret` only caught `CredentialError`). `KeyringCredentialStore` now
  raises a clean `CredentialError` → resolved to keyless, not a crash; status
  reports `store_unavailable`.
- **fix(pubmed): capture search diagnostics.** `esearch` now surfaces the true
  total count, NCBI query translation, and `warninglist`/`errorlist`. A
  malformed query (`lung cancer AND (`) is flagged (`warnings`) or degrades
  (`pubmed_query_error`) instead of silently staging unintended hits. Carried
  onto the intake record + printed by the CLI. The exact query is still preserved.
- **fix(writeback): capability-honest previews + audited failures.** Backends
  expose `supports(kind)`. A preview for an op the backend can't perform (e.g.
  `note_add`/`tag_add` on the web_api backend) now fails **early** with
  `operation_unsupported` and mints **no** token, instead of previewing success
  then failing on confirm. Every failed write attempt (unsupported, unavailable,
  backend error) now appends a `zotero.write.failed` audit event.

## 0.2.0 — write-back + secure onboarding

- **feat(writeback): Zotero Web API item-creation backend.** `WebApiWriteBackend`
  (api.zotero.org) creates items (`item_add` / `intake_push`) and assigns them to
  a collection at creation. `make_backend` wires `web_api` when enabled with
  credentials resolved from env/keyring; missing creds → UnavailableBackend (no
  silent fallback). All write guards intact (dry-run default, one-use token,
  audit, honest degradation).
- **feat: secure onboarding (`zotsynth onboard`).** Non-secret identifiers
  (PubMed email, Zotero user/library id, default collection) → config; secret
  keys (Zotero write key, NCBI key) → OS keyring via `keyring`, with
  `ZOTSYNTH_*` env escape hatch. Secrets are validated, then stored, and never
  written to config/logs/history or echoed. Adds `credentials.py`,
  `onboarding.py`, config fields, and the `keyring` optional dependency.
- **fix: resolve citekeys from Better BibTeX CSL-JSON (`item.search`).** The
  shared resolver (map_bootstrap / extract / claim_check) now parses the Zotero
  key from the CSL `id` URI instead of a non-existent `itemKey` field; contract
  test pins the real response shape.

## 0.1.1 — patch

- **fix(pubmed): efetch DOI from the article's own id list, not cited
  references.** efetch parsing used `.//ArticleIdList/ArticleId`, which descends
  into `PubmedData/ReferenceList` and could surface a *cited reference's* DOI as
  the article's DOI. Now scoped to the article's own `PubmedData/ArticleIdList`.
  Citation-integrity fix surfaced by a live `literature_search` run; covered by a
  regression test with decoy reference DOIs.
- Package metadata and runtime `__version__` bumped to `0.1.1`.

## 0.1.0 — integrity spine (steps 1–9)
> The `0.1.0` line was released from the build below (internally versioned 0.7.0
> during development, then aligned to 0.1.0). Tag: `v0.1.0-integrity-spine`.

### Build detail — steps 1–9 (the dev-internal "0.7.0" build)

### Step 1 — probe layer + state (`bbc0b37`, hardened in `319cd88`)
- Startup probe (probe-not-proof): Zotero `/api/` (read-only/GET-only), Better
  BibTeX `api.ready`, CAYW `probe=1`, with remediation strings.
- Honest version parsing: Zotero app version from `x-zotero-version`; schema
  version (`42`) and local-API version never surfaced as the app version; BBT
  version read live from `api.ready` (`betterbibtex` field), never hardcoded.
- `.zotsynth/` state layer: `config.json`, version-stamped frames, evidence map
  + citekey-centered reverse index, per-rating records, snapshots, intake,
  prisma, and a hash-chained `audit_log.jsonl`.
- Binding validators: model-pin-required, rating-vs-assist task split,
  frame/subject keying, and the rating-record validity invariant.

### Step 2 — read/discover + cite (`778d3f8`)
- Read-only `zot_search`/`zot_item`/`zot_collections`/`zot_attachments` honoring
  the personal/group/all library selector; honest degradation when absent.
- `cite` resolves citekeys by exact match via Better BibTeX; never invents keys.

### Step 3 — bib_sync + evidence map (`5f7d7e5`)
- `bib_sync`: multi-file Pandoc/LaTeX citekey extraction (code/URL/email masked),
  exact-match resolution, orphan/unused reporting, per-file + master exports,
  honest degradation.
- Operational evidence-map model: typed nodes/attachments with per-kind scope
  rules and a citekey-centered reverse index; all mutations audited.

### Step 4 — extraction + claim_check (`e2ef3ce`)
- Deterministic passage retrieval over Zotero full text + annotations.
- `extract`: assistive regex/rule extraction with passages; unverifiable when
  absent; never guesses; never writes the evidence map.
- `claim_check`: lexical support only — `supported_candidate` / `no_support_found`
  / `unverifiable`; never asserts truth; never invents keys.

### Step 5 — PubMed intake + manual import (`50b9db5`)
- PubMed-only provider (E-utilities) with rate-limit (3/10 rps) + 429 retry and
  honest degradation (`missing_ncbi_email` / `pubmed_unavailable`).
- `literature_search` (verbatim user query) + `import_results` (RIS/CSV/BibTeX),
  dedupe (in-run / prior-intake / library by DOI+PMID, never title-only),
  pre-decision intake records (`decision: null`).

### Step 6 — snapshot / corpus_diff / surveillance / map_bootstrap (`e5abf40`)
- `snapshot`: hashed read-only corpus + evidence-map capture; never invents
  citekeys; no fake snapshot when Zotero is down.
- `corpus_diff`: identity-continuity diffing; reverse-index-driven staleness.
- `surveillance_refresh`: re-run a saved query from its own last-run date
  (mechanical date append, not a redesign).
- `map_bootstrap` (minimal): section/study/explicit-outcome seeding; dry-run
  default; orphans never invented.

### Step 7 — dual-rating + assess + retraction + PRISMA (`e197ea4`)
- Dual-rating engine (`rating_start`/`commit_human`/`run_ai`/`compare`/
  `adjudicate`): blinded advisory AI behind an `AiRater` seam; the hardening
  invariants enforced and audited.
- `assess`: human-chosen controlled values only; tag-mirror deferred to step 9.
- `retraction_scan`: DOI/PMID via a provider seam (no title-only truth).
- `prisma_ledger`: human-only decisions; AI votes referenced by `rating_id` only.

### Step 8 — evidence export + agreement report (`d45f916`)
- `evidence_export`: neutral CSV/Markdown/CSL-JSON; AI values excluded by
  default and clearly labelled/separated when requested; mutates nothing.
- `agreement_report`: raw agreement, Cohen κ, ordinal weighted κ (ROBINS-I
  *No information* excluded + reported), adjudication rate; refuses κ across
  mixed schemes; PRISMA-trAIce / RAISE-style transparency section that disclaims
  any compliance/endorsement claim.

### Step 9 — guarded Zotero write-back (`fcbaf18`)
- Optional write layer: dry-run default, payload-bound one-use confirmation
  tokens, distinct `zotero.write.applied` audit event, **no silent fallback**.
- Tools: `note_add`, `annotation_add`, `item_add`, `tag_add`, `tag_remove`,
  `collection_add_item`, `intake_push`, `assessment_tag_mirror` (mirrors only
  human/final values; replaces prior same-scheme tag). Live default backend is
  clearly degraded (`write_layer_unavailable`); no network writes.

### Testing
- 308 tests **at this first milestone** (the suite has grown to 544 by 0.12.0),
  fully offline (fake Zotero/BBT/PubMed/write/AI seams). No live PubMed calls and
  no live Zotero writes occur during the suite.
