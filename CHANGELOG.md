# Changelog

All notable changes to CiteVahti (a product of Vahtian; formerly developed as
ZotSynth). The project was built in reviewed steps, each on its own branch off the
previous one.

## [Unreleased]

### Added
- **Static analysis in CI (`ruff`).** A new `lint` job runs `ruff check src` on every
  push/PR, gating merges alongside the test suite. Config lives in `pyproject.toml`
  (`[tool.ruff]`); `ruff` is in the `dev` extra. Rules: `E`/`F` (correctness, dead code)
  plus **`S` (flake8-bandit security rules)** — a security regression now fails CI like a
  syntax error. No behaviour change: the 19 auto-fixable dead-code findings (unused imports,
  a placeholder-less f-string) were removed, and the 6 remaining security findings were each
  triaged and annotated inline — 3 false positives (keyring/env-var *names*, a shell-free
  `subprocess` list call) and 2 genuine hardenings deferred to scoped follow-ups (`S310`
  TSA-URL scheme allow-list, `S314` defusedxml for PubMed parsing), each marked with a
  `TODO(security)` at the site. `E501` (line length) and `S110`/`S112` (best-effort
  try/except) are documented deferrals, not silent suppressions.
- **Type checking in CI (`mypy`).** A new `typecheck` job runs `mypy` on every push/PR.
  Config in `pyproject.toml` (`[tool.mypy]`, pydantic v2 plugin); `mypy` is in the `dev`
  extra. Gradual adoption: **146 of 162 files are type-checked and gating today**; the 16
  modules with pre-existing type errors are an explicit `ignore_errors` backlog (a ratchet —
  each follow-up types one module and removes it), not a blanket relaxation. No behaviour
  change. The largest item is `pubmed/provider.py` (one wrong return annotation → 14 errors);
  several backlog modules sit on safety paths (`tools.py`, `writeback/*`) and will be typed
  deliberately with the rating/writeback tests per `docs/SAFETY_INVARIANTS.md`.

### Security
- **Timestamp client now refuses a non-`http(s)` TSA URL (closes the `S310` deferral).**
  `Rfc3161Provider._post` validated nothing about the config-supplied `tsa_url` scheme, so a
  `file://` (or `ftp://`, `data:`…) URL would make `urllib.urlopen` read a local file instead
  of POSTing to a timestamp authority. It now rejects any scheme other than `http`/`https`
  with `TimestampUnavailable` *before* opening the URL. The `TODO(security)` deferral is
  gone; the `# noqa: S310` markers remain but are re-justified by the guard (bandit's blanket
  URL-open rule has no dataflow, so it can't see the upstream scheme check). New offline
  security regression
  (`test_timestamp.py::test_rfc3161_rejects_non_http_tsa_url_without_touching_the_filesystem`,
  marked `@pytest.mark.security`) proves a `file://` URL is refused without any network or
  filesystem access; documented in `SECURITY.md`.

### Fixed
- **Type ratchet — `bootstrap/service.py` (now type-checked).** Two non-bugs cleared: the
  order-preserving `_outcomes` dedup used the cryptic `seen.add(o)`-returns-`None` idiom
  (correct but flagged) — rewritten as an explicit loop; and the link-dedup key-set is now
  annotated `set[tuple[str, str, str]]` (a `LinkType` `Literal` is a `str` subtype; the set is
  only used for membership). No behaviour change. `bootstrap/service.py` off the `mypy` backlog
  (8 modules remain).
- **Type ratchet — `schemas/frame.py` (now type-checked).** `Scheme.ordinal_levels` sorted on
  `Level.ordinal` (`Optional[int]`) under a mismatched `# type: ignore[arg-type]`. The flag was a
  false alarm: `Level._check` (a pydantic validator) guarantees every non-`missing_like` level
  carries an ordinal, and the sort filters to exactly those — so the key is never `None` at
  runtime. Replaced the bogus ignore with an explicit, documented narrowing (no behaviour change).
  `frame.py` off the `mypy` backlog (9 modules remain).
- **Library dedupe missed DOIs in non-canonical form.** `ZoteroLibraryIndex.contains`
  searched Zotero with the *raw* DOI while comparing against the *normalized* one, so a
  manuscript DOI written `https://doi.org/10.1/ABC` could fail to match a library item stored
  as `10.1/abc` — reporting a duplicate as absent. Now searches with the normalized DOI
  (matching the comparison and the PMID branch). New regression test
  (`test_dedupe_zotero_index.py`) pins the search-uses-normalized-DOI contract; this also
  brought `intake/dedupe.py` off the `mypy` backlog (10 modules remain).
- **Type ratchet — `pubmed/provider.py` (now type-checked).** Corrected `_esearch`'s return
  annotation, which declared `list[str]` but always returned an `_EsearchResult` (the code
  already used it as one — the annotation lied; no runtime change), and made the esearch
  `count` parse handle a missing count explicitly. Removes the module from the `mypy`
  `ignore_errors` backlog (15 modules remain). PubMed search behaviour unchanged (covered by
  `test_pubmed_provider.py` + `test_pubmed_search_diagnostics.py`).
- **Type ratchet — 4 more modules type-checked** (`state/store.py`, `pubmed/parse.py`,
  `intake/manual.py`, `export/agreement.py`; backlog now 11). All annotation-only or
  behaviour-identical: an implicit-`Optional` parameter made explicit (`save_transaction`'s
  `event`); a `None`-guard reordered so the parser narrows `MedlineCitation` (same outcomes);
  and three container annotations (`dict[str, Any]`, `Counter[str]`). No runtime change.

## 0.42.0 — source reuse rights (`license-scan`) (2026-06-28)

- **Each candidate can now carry its reuse rights** — `oa_status` (gold/green/hybrid/bronze/
  closed) and `license` (e.g. `cc-by`) — filled from **OpenAlex** (the service CiteVahti already
  calls for retractions), by DOI/PMID. `citevahti license-scan [--json]`, a panel **⚖ Scan
  licences** button (`POST /api/candidates/scan-licenses`), and a neutral licence/closed chip on
  the candidate card; the API now returns the two fields.
- **Reports, never decides.** It records what the source's licence *is* so a human — or a
  downstream tool like a content hub — can judge reuse; CiteVahti never says a source is OK to
  republish. Unknown/offline leaves the fields unset (never a false "closed"/"reusable"). No new
  egress (OpenAlex was already disclosed). Audited as `license.scan`.
- 6 offline tests (`test_license_scan.py`): OpenAlex extraction, closed→no-licence, honest
  unknowns, the scan fills/audits, and unknown stays unset. Verified live end-to-end through the
  panel.

## 0.41.0 — tufup auto-updater scaffold for the desktop app (2026-06-27)

- **Signed auto-updates** for the frozen desktop app, built on `tufup` → The Update Framework
  (`src/citevahti/autoupdate/`, the `update` extra). Updates are signed metadata + hashes, so a
  client accepts a new version only if it was signed by CiteVahti's offline keys — integrity even
  if the update server is compromised. The maintainer flow (`maintainer.py`) keeps the `root`/
  `targets` trust-anchor keys **offline** (the TUF key split); the client (`client.py`) checks and
  applies, degrading to a clear status on any error.
- **Inert and safe until configured.** With no update URL and no bundled trusted root (the state
  until the founder generates keys + stands up the server), every entry point is a no-op — it
  never touches the network or affects a launch. Nothing is auto-applied silently: `check_for_update`
  is read-only; `apply_update` is the post-consent step. The desktop app surfaces an available
  update at launch (logged) without blocking.
- **`docs/AUTO_UPDATE.md`** documents the security model (the key split, why `root`/`targets` stay
  offline), the one-time key generation, the per-release sign-and-publish flow, and a
  key-management runbook (custody, rotation, compromise). 11 offline tests (inert path, graceful
  degradation, maintainer wiring, the launch hook never breaks a launch) — no tufup or network
  needed in CI. STATUS egress disclosure updated.
- **Founder-gated next steps** (flagged, not silently assumed): generating the offline keys,
  standing up the update server, and the Apple/Windows *code-signing* of the bundle (a separate
  signature from tufup's metadata signing) — see the secure-release skill.

## 0.40.0 — `claim-verify`: offline claim-vs-text check (2026-06-27)

- **`citevahti claim-verify --claim "…" --text-file src.txt --json`** — checks a claim against
  **provided text, fully offline (no Zotero, no ledger)**. The companion to `claim-check` for
  the integration case where the caller already has the cited source's text (an external
  citation reviewer typically does). Source text comes from `--text`, `--text-file`, or stdin.
  Returns the deterministic lexical-overlap result — `coverage`, `status`
  (`terms_present`/`terms_missing`), present/missing terms, and a `contradiction` + inspectable
  `polarity_cue` when a sentence carries the claim's terms with the opposite polarity. **Never
  a verdict.** Exit `0` when the check ran.
- `docs/INTEGRATION.md` updated: `claim-verify --json` is now the documented offline seam (was
  previously in-process only). Locked by two `test_cli_json.py` tests (stable shape + the
  polarity cue is surfaced, not auto-judged).

## 0.39.0 — `claim-check --json`: a stable citation-verifier contract (2026-06-27)

- **`citevahti claim-check --json`** emits the full `ClaimCheckResult` as JSON on stdout (no
  human lines), so another tool can use CiteVahti as a citation-verification backend without
  scraping text. The schema is the stable contract: the 4-state `aggregate_status`
  (`supported_candidate` / `contradiction_candidate` / `no_support_found` / `unverifiable` —
  **never a binary pass/fail**), per-citekey detail, and provenance. Exit code is `0` unless
  the result is `unverifiable`.
- **New `docs/INTEGRATION.md`** documents the verifier seams (the `--json` CLI, the in-process
  `claim_lexical_check` / `claim_check` engine functions, the MCP `verify_claims` tool), the
  "never asserts truth" semantics to preserve, the recommended mock-first adapter pattern
  (`CITATION_VERIFIER=local|citevahti`, pin the version), and what *not* to integrate against
  (the loopback panel; FullVahti).
- Contract locked by `test_cli_json.py::test_claim_check_json_is_a_stable_verifier_contract`.

## 0.38.0 — deterministic blinding: one rule, all surfaces (2026-06-27)

- **The blinding rule is now single-source.** Blinding — keeping the AI rating hidden until
  the human rates — is CiteVahti's core safety property, but the reveal logic was *duplicated*
  in three places (the loopback panel's `blinded_rating_view`, the agent's `get_provenance`,
  and the report's `claim_report`). Coincidentally consistent, but a future edit to one could
  leak the AI value on that surface while the others' tests stayed green. All three now derive
  blinding from one canonical, pure, **deterministic** function (`rating/blinding.py`:
  `reveal_ai` / `blinded_ai_value`) — reveal iff a human rating exists, with no dependence on
  timing, ordering, or randomness. Each surface keeps its own display wording; only the
  *decision* is centralized, so outputs are byte-for-byte unchanged.
- New tests lock it: `test_blinding_deterministic.py` (the pure rule — state-based, idempotent,
  the AI value never affects the reveal decision) and
  `test_panel_api.py::test_blinding_is_consistent_across_surfaces` (panel == provenance ==
  report agree, and the AI value leaks from none of them). Both join the `security` group
  (now 32 tests). `docs/SAFETY_INVARIANTS.md` + `SECURITY.md` record the invariant.

## 0.37.0 — per-session CSRF token for localhost writes (2026-06-27)

- **The loopback panel now requires a per-session CSRF token on every state-changing request**
  (`X-CiteVahti-Token`), layered on the existing `Host`/`Origin`/`Content-Type` checks. The
  token is minted per server process, served to the legitimate page at `GET /api/session`, and
  compared in constant time. It's a *positive* secret check — robust even if the Origin/Host
  allow-list parser ever mishandles an adversarial header value — and the client's `api()`
  helper sends it automatically, so it costs the user nothing. First item on the founder's
  pre-public-beta security roadmap. (Items #1 Origin/Host validation was already shipped and
  test-guarded; this completes the localhost-write hardening pair.)
- Guarded by `tests/test_panel_csrf.py` (now 7 tests: missing-token → 403, wrong-token → 403,
  valid-token → 200, plus the existing Host/Origin/Content-Type cases). `docs/SAFETY_INVARIANTS.md`
  records it as a supporting invariant.
- **Honest limitation:** the token does not stop a non-browser local process running as the
  user (already past a single-user tool's trust boundary); its value is against browser attacks
  and parser edge cases.

## 0.36.0 — "Check for updates" in the panel (2026-06-27)

- **A "⬆ Check for updates" button in the panel's Tools menu** — surfaces 0.35.0's
  `check-update` to the non-technical researcher who lives in the panel, not the terminal.
  It calls PyPI **only on click** (new `GET /api/check-update` → `engine.check_update()`),
  never on load — so the no-silent-egress posture is preserved. Up-to-date dismisses on its
  own; an available update stays pinned with the upgrade steps; an unreachable PyPI is
  reported calmly, not as a crash.
- Egress disclosure (README + `docs/STATUS.md`) now names the panel button alongside the CLI
  command and agent tool. Endpoint routing is test-guarded
  (`test_update_check.py::test_panel_endpoint_routes_to_check_update`) and the suite stays
  offline.

## 0.35.0 — `check-update`: is a newer release out? (2026-06-26)

- **New `check-update` CLI command + `check_update` agent tool** — ask PyPI whether a newer
  CiteVahti is published. Read-only, **user-initiated** (no launch-time or background
  phone-home), sends no data about you, and **never installs** anything; it just reports
  current vs latest with a plain-language next step. The companion to 0.34.3's running-version
  readout: `status` says what you're *running*, `check-update` says what's *available* — so
  together they answer "am I up to date?", the recurring stale-`.mcpb` pain.
- **Honest egress disclosure** updated in README + `docs/STATUS.md`: the one new outbound call
  is the opt-in PyPI check. Network goes through the existing `HttpClient` seam, so the test
  suite stays fully offline (`tests/test_update_check.py`).
- The desktop-app / panel surfacing of the check is a deliberate follow-up (it involves a
  UI-egress placement decision) — this release ships the reusable core (engine + CLI + agent).

## 0.34.3 — confirm which build is running (2026-06-26)

- **`status` now reports the running `version`** as its first field, and the MCP server
  prints `citevahti-mcp v<version>` on startup. After (re)installing the `.mcpb` in Claude
  Desktop you can now check that the latest build is actually live — Claude Desktop can
  keep the previously-installed extension cached, so an upload alone didn't tell you which
  version was running.
- **README — "Updating" gained a Claude Desktop note**: if `status` shows an old version,
  remove the existing CiteVahti extension, fully quit and reopen Claude Desktop, then add
  the newest `.mcpb` and re-check `status`.

## 0.34.2 — README install front-door (2026-06-25)

- **A "Which one?" pointer** at the top of *Start here*: Claude Desktop extension (one click,
  no terminal) · the standalone **desktop app** · pip — all driving the same review.
- **Documents the standalone desktop app** (`pip install 'citevahti[app]'` → `citevahti-app`),
  which shipped across 0.29–0.32 but was never in the README: a native window (no browser, no
  Claude Desktop), drag-a-manuscript to start, optional local-Ollama AI. Honest about needing
  the terminal once to install. Docs-only — no behaviour change; ships the clearer guidance to
  the PyPI page (the README is the long description).

## 0.34.1 — author pathway: remove two dead-ends (2026-06-25)

- **The chat's "no model configured" is no longer a dead-end.** When the chat returns
  `ai_off`, it now offers a **⚙ Set up a model** button that opens AI settings (which
  recommends a local Ollama model) — so a standalone user has a one-click path to a working
  model instead of a flat message.
- **First-run leads with drag-and-drop.** The empty-state now says *"Drag a `.md` or `.docx`
  onto this window"* first — surfacing the 0.30.0 capability that was the easiest no-terminal
  way to start but went unmentioned. (Author-pathway polish; no behaviour change to the
  blinded review.)

## 0.34.0 — "Draft from claims" pulls your vetted claims automatically (2026-06-25)

- **The "Draft from claims" skill now gathers your accepted claims and their citekeys for
  you** — no pasting. A new read-only `GET /api/draft-context` (`engine.draft_context`)
  lists each **accepted** claim with the citekey to cite it by (the stable key minted from
  the paper's PMID/DOI — your own Better BibTeX key is still resolved by cite-export). An
  accepted claim with no identifier is returned `cited: false` and flagged "needs a source"
  — **never given an invented citekey**.
- Read-only and advisory: it records nothing and writes nothing (locked by the
  read-only-surface invariant test), and it only feeds the chat skill, which still offers a
  draft to review and never edits the manuscript. Loop iteration 2 (turning vetted claims
  into writing).

## 0.33.0 — writing-assistance skills: turn vetted claims into prose (2026-06-25)

- **The Prompts & chat panel now has a "Writing" group** of advisory skills for turning
  vetted claims into manuscript prose: **Draft from claims · Improve structure · Improve
  transitions · Check spelling**. Run any against your configured model (local Ollama / API).
- **Advisory and aligned by construction:** each skill offers *suggestions to review*, never
  edits the manuscript silently (the chat records and writes nothing), uses **only the
  citekeys you provide** — never invents or drops a citation — keeps each claim's meaning,
  and makes **no** truth/quality/publication-readiness claim. An uncited claim is flagged as
  needing a source, not given an invented one; spelling flags technical terms and citekeys to
  "check" rather than changing them. The prompts are grouped (Review vs Writing) in the panel.

## 0.32.0 — a small in-app chat with your configured model (2026-06-25)

- **The Prompts panel is now "Prompts & chat":** a small chat that talks to your **configured
  model** — a local **Ollama** / LM Studio model (nothing leaves your machine) or your own API
  key — reusing the same connection plumbing as the AI rater. Each preprogrammed skill gets a
  **▷ Run in chat** button; or just type. Returns a clear "configure a model" message when AI
  is off (`POST /api/chat`, `engine.chat`).
- **Advisory only, by construction:** the chat records nothing, calls no tools, and writes
  nothing (a test asserts the audit ledger is unchanged after a turn). Its framing keeps the
  model neutral — it must not declare whether a source supports a claim before you rate, and
  makes no truth/quality claim. The human still rates and decides in the panel; the blinded
  rating path is untouched. It sends only what you type to the model you configured (local
  Ollama = fully local).

## 0.31.0 — a prompt panel: the preprogrammed skills, one click (2026-06-25)

- **New "✦ Prompts" panel** (Tools menu) surfaces the preprogrammed agent skills —
  **run claim tests · screen a topic · check a paragraph · methods statement** — as
  one-click, copy-to-paste cards, each with its description. Paste into your chat client,
  or a local model via Ollama. Backed by a read-only `GET /api/prompts`; the deprecated
  `review_manuscript` alias is not advertised.
- Runs no model itself — it's the preprogrammed-prompt launcher. (A small in-app chat that
  *runs* these against a local Ollama model is the planned next piece; its model-backend
  is a separate, deliberate choice.)

## 0.30.0 — drag-and-drop a manuscript onto the panel (2026-06-24)

- **Drop a `.md`/`.markdown`/`.txt`/`.docx` anywhere on the panel window to open it** — a
  full-window dropzone routes the file into the existing import-review flow (`.docx` is
  converted server-side; text opens as-is). Works in the native desktop window
  (`citevahti-app`) and the browser panel alike; available even on the empty first-run
  screen, since dropping your first manuscript is the point. Slice 2 of the desktop-app goal.
- Refactor only: the file picker and the dropzone now share one `importFile()` path; the
  import endpoints and review modal are unchanged. No new dependency.

## 0.29.0 — native desktop window: `citevahti-app` (not a browser) (2026-06-24)

- **New `citevahti-app` launcher opens the review panel in a native OS window** — WKWebView
  on macOS, WebView2 on Windows, WebKitGTK on Linux — instead of a browser tab. It reuses
  the exact same panel and every guarantee (loopback-only, single-user, human-first); only
  the shell changes. `pip install 'citevahti[app]'` (pywebview is an optional extra; the
  core install and the browser/MCP surfaces are untouched).
- First slice of the desktop-app goal: the launcher starts the panel on an ephemeral
  loopback port with **no browser** and shows it in a sized, titled window. Still to come:
  drag-and-drop a manuscript onto the window, and a signed double-clickable `.app`/`.exe`/
  AppImage build (reusing the existing PyInstaller + notarization pipeline). The native
  window needs a display, so it's verified by wiring (fake-webview tests) here and on your
  machine in practice.

## 0.28.1 — desktop extension advertises all four agent prompts (2026-06-24)

- **Fixed: the `.mcpb` manifests advertised only 2 of the 5 registered prompts**, so a
  Claude Desktop user couldn't discover `check_paragraph` (0.25.0) or `methods_statement`
  (0.26.0) even though the server served them. Both `manifest.json` and
  `manifest.binary.json` now list all four canonical prompts (the deprecated
  `review_manuscript` alias stays intentionally unadvertised).
- The parity test that should have caught this had a **hardcoded stale expected set**; it
  now checks every canonical prompt name, so the manifest can't silently drift behind the
  server again. (Icons were already correct: `.mcpb` `icon.png`, panel `favicon.svg` +
  `apple-touch-icon`, VS Code `icon.png`.)

## 0.28.0 — evidence-basis chip on the review card (2026-06-24)

- **The review card now shows the evidence basis at rate time** — a neutral chip on each
  candidate: **◐ abstract only**, **● full-text passage**, or **○ no text staged**. This
  puts "you're rating against the abstract, not the full text" in front of the human
  exactly when they rate, instead of only in the methods statement (0.24.2). Derived with
  the same rule: a rating anchored to a located `PassageRef` is full-text; otherwise the
  candidate's abstract is what's available.
- Honest, not a verdict: the chip is **metadata, styled neutrally** — it never reuses the
  support-state colours and makes no truth/quality claim; the tooltip says to confirm
  against the full text before relying on the citation. `/api/claims/<id>` now returns
  `evidence_basis` per candidate.

## 0.27.0 — sealed-envelope pre-screening: the agent may rate first, withheld (2026-06-24)

- **The agent prompts now let pre-screening produce the LLM rating corpus without anchoring
  the human.** Previously `run_claim_tests` required the agent to submit its support rating
  *only after* the human's — chronological human-first. That made the tool a stopper for a
  legitimate workflow: an agent pre-screening candidates and recording its own (blind)
  ratings first. The blinding is now correctly framed as **sealed-envelope**: the agent may
  record its support rating first with `submit_ai_support_rating`; the engine **seals it and
  keeps it hidden until the human rates**, and the agent must **present candidates neutrally**
  so its sealed rating never leaks — the human still rates fully unanchored.
- No engine change — `support_run_ai`/`submit_ai_support_rating` already had no human-first
  ordering guard, and `blinded_rating_view` already returns `"hidden (blinded until human
  rates)"`. This release aligns the **prompts, the ordering test, and the docs** with that
  sealed model. Every safety invariant holds: AI value never becomes the final value, the
  human owns the decision, the human is never anchored, and Zotero writes stay
  previewed/confirmed/undoable. `screen_topic` still records no rating itself (it proposes
  leads); the sealed pre-rating happens in `run_claim_tests`.

## 0.26.0 — a methods-statement agent skill (2026-06-24)

- **New MCP prompt `methods_statement`** — companion to the `check_paragraph` skill (0.25.0).
  A researcher can now ask the assistant to produce the paste-ready **methods text** from
  the ledger: the blinded human→AI→adjudication workflow paragraph, the PRISMA "how the
  literature was found" AI-disclosure (model + snapshot, leads-only role), and the
  flow-of-evidence counts table. The `methods` tool shipped in 0.24.0–0.24.9 but had no
  guided prompt skill; this makes it discoverable.
- **Safe by construction:** read-only (calls only the read-only `methods` tool — no AI, no
  network), records nothing, reveals no AI rating, and the prompt explicitly frames the
  output as *documenting the workflow and disclosing AI use* — **not** asserting the
  manuscript is true, correct, or publication-ready. It surfaces `(unset — …)`/`n/a`
  markers for the researcher to fill, never invented. Adds no tool/capability (agent
  surface guard unchanged).

## 0.25.0 — an everyday "check this paragraph" agent skill (2026-06-24)

- **New MCP prompt `check_paragraph`** — the everyday in-writing loop (shipped as a tool in
  0.23.0) is now a first-class, discoverable agent skill for researchers. Paste a paragraph
  you're drafting and the assistant reports, per claim-like sentence, what's already vetted,
  what needs attention, and what's new — then hands real work off to `run_claim_tests`.
- **Safe by construction:** the prompt is read-only — it calls only the read-only
  `check_paragraph` tool (no AI, no network) and routes anything that needs work into the
  blinded, human-first claim-test flow (human rates first → AI second → preview → confirm →
  undo). It rates/decides/writes nothing, reveals no AI value, and says plainly that
  "reviewed" means the citation *support* was reviewed — **not** that the claim is true or
  the manuscript is publication-ready. Adds no new tool/capability (the agent surface guard
  is unchanged).

## 0.24.9 — the read-only methods view no longer writes exports (2026-06-24)

- **Fixed a read-only-contract violation found by a new safety test.** Building the
  methods statement (`citevahti methods` / the read-only `methods` chat tool) called the
  agreement report, which *always* wrote export files under `.citevahti/exports/` and
  appended an `export.agreement` audit entry — so merely *viewing* the methods paragraph
  mutated the ledger and littered the audit trail with phantom exports. The methods
  builder now computes those numbers with `AgreementReportService.report(persist=False)`;
  the explicit `agreement-report` / `evidence-export` paths are unchanged.
- **New test `test_readonly_tools_dont_mutate.py`** locks the contract: `claim_report`,
  `triage`, `methods_statement`, and `check_paragraph` leave the audit log and every
  ledger file byte-identical. Recorded as a supporting safety invariant.

## 0.24.8 — a PRISMA flow numbers table in the methods statement (2026-06-24)

- **The methods statement now includes a PRISMA-style flow-of-evidence table** — the
  larger companion to the LLM-discovery paragraph (0.24.0) and the abstract-vs-full-text
  basis line (0.24.2). Counts are derived from the ledger for the PRISMA diagram's
  *identification → screening → included* boxes: records identified (returned across the
  database searches) → records staged as candidate evidence → claim–evidence pairs
  assessed (human-rated) → supporting citations included (claims with accepted evidence).
- Honest by construction: it states plainly that CiteVahti works at the **claim** level
  (each claim is a separate question), so the counts aggregate across the manuscript and
  are **not** de-duplicated across searches — adapt to your review's unit before reporting.
  No schema change; rides `citevahti methods` / the `methods` chat tool.

## 0.24.7 — a non-color design-token scale for the panel (2026-06-24)

- **The panel now has spacing, radius, type, and elevation tokens (audit §B).** The CSS
  had ~30 color tokens but *zero* for the rest — ~575 hardcoded `px`, 65 `border-radius`,
  inline shadows. Added a scale extracted from the existing literals (values unchanged):
  spacing (`--zs-space-2xs…2xl`), radius (`--zs-radius-xs…pill`), type (`--zs-text-2xs…lg`),
  and elevation (`--zs-shadow-1/2/3`).
- Migrated the bounded, property-anchored categories to the tokens: **all `box-shadow`s**,
  **border-radius** (46 of 65; the off-scale 3/5/7/9 px left as literals), single-value
  `gap`, and standalone `font-size`. Visual output is unchanged (verified in the panel);
  this is an internal consistency pass so future styling has a vocabulary to reuse. The
  remaining padding/margin literals can adopt the spacing scale incrementally.

## 0.24.6 — one shared root resolver across all surfaces (2026-06-24)

- **The CLI, the MCP server, and the panel now resolve the project root the same way
  (audit §A.1).** Previously two resolvers disagreed: chat/CLI fell back to *home* while
  the panel fell back to *recents/cwd*, and only the panel consulted the last-used root —
  so the same machine could answer "what am I working on" two different ways. There is now
  one `rootcfg.resolve_root()` with a single precedence: explicit `--root` → `$CITEVAHTI_ROOT`
  → cwd-with-ledger → last-used root (with ledger) → home. Chat and panel now agree.
- The last-used root and `has_ledger` moved into `rootcfg` (re-exported from `panel.prefs`
  for compatibility); `prefs.resolve_default_root` is a thin wrapper over the shared resolver.
- Safety preserved: bare cwd is still never the fallback (the desktop launches the MCP
  server from `/`), so a launch from `/` resolves to your last-used ledger, never `/`.

## 0.24.5 — jumping to a claim opens its manuscript (2026-06-24)

- **Fixed the cross-manuscript desync (audit §A3).** A manuscript holds only a few claims
  (a primary outcome and a few secondary), so the ledger spans several — and a triage row
  or a `?focus=` deep-link often targets a claim in a *different* manuscript than the one
  open. The claim card switched but the document pane didn't. Now `selectClaim` loads the
  claim first, reads its `manuscript_id`, and switches the document pane (and switcher
  highlight) to that manuscript so prose and card stay in sync.
- `/api/claims/<id>` now returns `manuscript_id` (the same key the switcher groups by);
  the deep-link no longer drops a `?focus=` that points outside the current manuscript.

## 0.24.4 — the panel reopens the manuscript you were on (2026-06-24)

- **Completes the manuscript switcher.** The manuscript you open is now remembered
  per-project (`panel.json` `active_manuscript`; `prefs.remember_manuscript` /
  `recall_manuscript`), so a reload reopens *it* instead of snapping back to the first
  (claims-heavy) entry. `/api/manuscripts` returns `active`; opening a manuscript records
  it; a remembered manuscript that's no longer present is ignored. One precedence now
  decides the working manuscript: just-added → open this session → last worked on →
  first in list.
- **Empty state.** When there are no claims and no documents in the bound folder, the
  switcher says "No manuscript yet — open your document folder, or add a claim to begin"
  instead of rendering a blank label.

## 0.24.3 — a manuscript you just added is selectable, not hidden behind the old one (2026-06-23)

- **Fixed: adding a new manuscript and "always getting the stale one you've been working
  with."** The panel's manuscript list was built *only from claims that already existed*,
  so a document you just added (zero claims yet) was invisible — leaving only the
  manuscript you'd already worked on. The list now also surfaces the `.md`/`.markdown`/
  `.txt`/`.docx` files actually present in the bound manuscripts folder
  (`manuscript.list_manuscript_files`), each selectable with a `0` claim count; selecting
  one opens its real prose so you can start extracting claims.
- **The just-added manuscript now becomes the active one.** Importing/pasting a document
  focuses it instead of sticking to the previously open manuscript, and binding a folder
  jumps to a manuscript that actually lives in it (`loadManuscripts(preferId)` in the
  panel). Companion to the working-file-selection design note (ADR-0007/0002).

## 0.24.2 — methods statement states the abstract-vs-full-text evidence basis (2026-06-23)

- The methods statement now reports the **evidence basis** of its ratings — borrowing
  MatchVahti-Lite's "capture first · verify before citing" honesty: *"Of N rated
  claim–candidate pair(s), K were assessed against at least one located full-text passage
  … and J against the candidate abstract retrieved from PubMed. Abstract-only support is
  provisional — confirm such claims against the full text before relying on the citation."*
- Derived from existing data, **no schema change**: a rating that carries a quoted
  `PassageRef` (attachment + character offsets) is full-text-anchored; one with no passages
  was assessed against the abstract the blinded rater saw. Honest by default — when the
  whole ledger is abstract-only, it says so plainly (and most PubMed-only reviews are).

## 0.24.1 — name the discovery model's snapshot, not just its id (2026-06-23)

- The PRISMA "how the literature was found" disclosure now names the discovery model's
  **snapshot/version** alongside its id — e.g. *"(claude-opus-4-8, snapshot 2026-05-01)"* —
  because a model id alone is not a reproducible disclosure. Honest as ever: when the
  snapshot is not pinned it shows `(unset — pin ai_provenance.model_snapshot)`, never a
  fabricated version.

## 0.24.0 — PRISMA: document the LLM in literature discovery (2026-06-23)

- **`citevahti methods` (and a `methods` chat tool).** The submission-ready methods
  paragraph — auto-filled with this ledger's real numbers — is now viewable directly,
  not only as `methods.md` buried inside the review-packet `.zip`. Read-only; the same
  honest, never-invented text as before (`n/a` for missing agreement/κ, `unset` for an
  unpinned model).
- **New: a PRISMA-style "how the literature was found" disclosure.** When an LLM was in
  the discovery loop (topic screening / claim extraction via `screen_topic`), the methods
  statement now documents it under the *identification* step: the model named, its role
  bounded to **proposing leads** (it recorded no support rating and made **no eligibility
  or inclusion decision**), the honest counts of model-proposed vs author-identified
  claims and staged candidate references — and an explicit reminder to disclose the model
  and date of use. When no LLM discovery was used, it says so plainly. This closes the gap
  for systematic reviewers, who must disclose any AI assistance in study identification.
- `screen_topic` now points the assistant at `methods` for the PRISMA disclosure after a
  screening run, so the discovery step is documented rather than silent.

## 0.23.0 — check-a-paragraph: the everyday in-writing loop (2026-06-23)

- **`citevahti check-paragraph` (and a `check_paragraph` chat tool).** Paste a paragraph
  you just wrote and instantly see, per sentence, which claims you've **already vetted**
  (✓), which **need attention** (⚠ with the reason + next action), and which are **new /
  untracked** (•). Read-only, **no AI, no network** — it matches each sentence to the
  claims already in your ledger (exact normalized hash, then substring / token-overlap)
  and reuses the risk triage. Turns CiteVahti from a final-pass tool into a daily writing
  companion: "have I checked this?" while you write, not just before you submit.
- The chat assistant can run it on a snippet ("check this paragraph") and lead you to the
  ones needing attention, offering to add the new ones.

## 0.22.1 — triage in the panel (2026-06-23)

- **The panel now leads with a "⚠ what needs you" banner.** Above the manuscript it
  shows *"N of M claim(s) worth your attention · K clean · risk X/100 — review these
  first"*, worst-first, each row naming the reason; clicking a row jumps straight to that
  claim's review card. So the panel-living researcher sees the few that matter instead of
  scrolling every claim. Read-only (`GET /api/triage`); hidden when nothing needs attention.
  Completes the triage front door across all three surfaces (CLI · chat · panel).

## 0.22.0 — risk-first triage: "review the few, not all" (2026-06-22)

- **`citevahti triage` — the friendly front door.** Instead of asking you to review
  every claim, it surfaces only the few that need attention right now, **worst-first**,
  each with a plain-language **reason** and a concrete **next action** — e.g. *"A
  retracted paper sits behind this claim → replace the source", "Overstated → tighten
  the wording, then accept", "Raters disagree → adjudicate", "No accepted support yet →
  find evidence or revise"*. Built on the existing Epistemic Risk Score (`risk/triage.py`,
  `TriageReport`); read-only, advisory.
- **The chat agent leads with it.** New read-only `triage` MCP tool, and the
  `run_claim_tests` choreography now ends by presenting the triage list and offering to
  walk through the handful that matter — so a busy researcher fixes the 6 that could
  embarrass them rather than re-reading all 84.

## 0.21.6 — P1 polish from external QA (2026-06-22)

- **Human-only decisions need no `compare` step.** A human rating with no AI second
  opinion now resolves on its own, so `claim-decide` works directly — no more
  misleading "discordance has not been adjudicated" error when no AI ever rated.
- **AI-off is a clean error, not a traceback.** `claim-support-run-ai` with AI off now
  raises a typed `AIUnavailableError` (caught by the CLI) — "AI is off… continue
  human-only, or turn it on" — instead of a Python stack trace.
- **`citevahti doctor` shows the version + ledger root** and warns that docs describe
  the running version (helps when a guide is from a different release).
- **Better CLI help** for `init`, `verify-audit`, and `mcp-serve` (purpose + example).
- **VS Code extension: `npm audit` clean** (0 vulnerabilities; refreshed the dev-only
  `undici` transitive dependency).

## 0.21.5 — stable ledger root (fixes "config not found" under the desktop app) (2026-06-22)

- **Fix: the MCP server resolved `.citevahti/` relative to its launch directory.** The
  desktop app starts `mcp-serve` with an arbitrary cwd (often `/`), so even after
  `citevahti init` (run from home → `~/.citevahti`) every tool returned "config not
  found" — it was looking in the wrong place. The default root is now a **stable**
  location: `$CITEVAHTI_ROOT` if set, else the **home** directory (`~/.citevahti`) — never
  cwd. The CLI and the MCP server share one resolver, so `init` and `mcp-serve` agree from
  any directory, with no `--root` hand-editing of `~/.claude.json`. Pass `--root` for a
  per-project ledger.
- `citevahti --version` and `python -m citevahti` now work (basic install verification).

## 0.21.4 — P0: tamper-resistant decision state (2026-06-22)

- **Security (P0): a decision file edited outside CiteVahti could make an unsupported
  claim read as accepted.** Manually flipping `.citevahti/decisions/*.json`
  `final_decision` from `reject` to `accept` (on a `does_not_support` rating) made the
  claim show **accepted**, passed `test`, and produced a Zotero **write preview** — while
  `verify-audit` still reported the chain intact (the hash chain covers the LOG, not the
  materialized state). Found by external QA, reproduced on PyPI 0.21.3.
  - The report / `test` / write paths now **revalidate every decision against its rating
    on use** (`decision_inconsistency`): an inconsistent decision is **not counted as
    accepted**, the claim is flagged (`row.inconsistent` + a report-level warning), the
    **write is refused** (no preview, no Zotero write), and the manuscript test **fails
    loudly** with a `ledger_integrity` check. Catches both flipping `final_decision` alone
    (internal check) and flipping it together with `final_support_status` (rating
    cross-check).
  - **`verify-audit` upgraded** to a full integrity check: it now also validates that
    every decision file agrees with its rating, and exits non-zero on any inconsistency
    ("…edited outside CiteVahti; reports and writes are blocked until the ledger is
    repaired").

## 0.21.3 — agent can pin its model; deterministic MCP root (2026-06-22)

- **`init` can pin the agent's model.** After `init`, AI-extracting tools
  (`propose_claim` / `propose_revision`) were gated on a pinned provenance model —
  but a pure agent flow had no way to set one (only the panel ✦ AI did), so an
  agent-driven validation stalled right after init. `init(model_id="…")` now pins
  the model (snapshot defaults to the model id) in the same bootstrap call, and the
  `model_not_pinned` error names that fix.
- **Deterministic MCP root.** `citevahti-mcp` now resolves its root as `--root` →
  `$CITEVAHTI_ROOT` → cwd, to an **absolute** path, and **logs it on startup**
  (stderr) — so `init` and every tool agree on one ledger location regardless of the
  launch directory.

## 0.21.2 — agent `init`, a working AI second opinion, optional decision reason (2026-06-22)

- **Fix: the MCP/agent surface couldn't initialize.** Every tool needs the ledger,
  but `init` was not a registered tool — an agent (or any no-terminal client) hit a
  dead-end where the error said "run init() first" with nothing to call. Added an
  idempotent **`init` tool** that creates `.citevahti/config.json` and reports the
  resolved root + config path (so it's clear *where* the ledger lives — the server's
  bound root, not the caller's cwd). The "not found" error now names a real action
  (`init` tool / `citevahti init`) and the path it checked.
- **Fix: the AI second opinion always abstained** because claim candidates were staged
  with titles only — the blinded rater (and the human) had no abstract to judge. The
  MCP search now fetches abstracts, and an AI run **backfills** a missing abstract from
  PubMed (and saves it). The support prompt also gained value definitions + PICO guidance.
- **Decision reason is now optional** — a sensible default is recorded if you don't type
  one, instead of blocking every decision.

## 0.21.1 — Word features work in the desktop app (no terminal) (2026-06-22)

- **Fix: Word import / Word report failed in the `.mcpb` with a `pip install
  citevahti[docx]` hint a no-terminal user can't act on.** `python-docx` is now a
  **core dependency** (not the optional `docx` extra), and the desktop bundle
  force-includes it, so Word import (`.docx → review`) and the integrity-report
  `.docx` work out of the box in Claude Desktop. The `[docx]` extra is kept as an
  empty back-compat alias. (Cite-stable export already worked — it uses Pandoc.)
- Dropped the stale "needs the docx extra" note from the panel's Export dialog.

## 0.21.0 — cite-stable export, group libraries, and the zero-setup demo (2026-06-20)

- **Cite-stable export — citations that survive copy-paste and Word.** A new
  `citevahti cite-export` (and a one-click **⎘ Cite-stable export** panel button)
  embeds a durable `[@citekey]` after each accepted claim in your Markdown and writes
  a matching `references.bib`, then can produce a `.docx` with live citations + a
  bibliography via Pandoc. Prefers your **own Better BibTeX citekeys** (so keys match
  your Zotero), minting a PMID/DOI key only as an honest fallback. Pandoc is fetched
  once at runtime (pypandoc) — never bundled — with a "Downloading Pandoc…" notice.
  It never cites a **stale bond** (a claim reworded after acceptance) or an
  identifier-less paper.
- **Group-library writes, done safely (review findings #2/#3).** `claim-commit
  --library personal|group:<id>` and a `citevahti.library` VS Code setting; the
  Zotero **account** user id is now kept separate from the target library (no more
  `/users/<group-id>`), and duplicate checks search the library the write targets.
- **`intake_push` dedupe honesty (#4).** When the Zotero search can't run, a
  confirmed staging write now refuses (`dedupe_unverified`) instead of silently
  risking duplicates — matching the validated path.
- **Zero-setup `citevahti demo`.** Builds a synthetic ledger + manuscript and opens
  the panel showing every claim state — no Zotero, MCP, AI, or network — so a
  first-timer can see the Rate → Reveal → Decide loop in three minutes.
- **Trust docs.** `KNOWN_LIMITATIONS.md`, `WRITING_GOOD_CLAIMS.md` (keep claims
  atomic), `SBOM.md` (lean dependency posture + how to regenerate/audit), and a
  "choose your path" router in the Quickstart.
- **Accessibility.** WCAG 2.1 AA pass on the panel (input labels, menu roles,
  status vs alert).
- Scrubbed personal paths from the first-run screenshot; the capture tool now runs
  with an isolated HOME so ledger discovery can't leak real paths.

## 0.20.0 — macOS one-click install, the UX adoption pass, and release provenance (2026-06-19)

- **macOS desktop install (signed + notarized, built in CI).** Releases now ship a
  `citevahti-<version>-macos-arm64.mcpb` alongside Windows and Linux — built on `macos-latest`,
  codesigned with the Developer ID (hardened runtime + entitlements) and notarized via
  notarytool, gated on repo secrets (an unsigned macOS download is blocked by Gatekeeper). The
  install cards point at the per-platform asset, and the docs note the one-time first-open
  Gatekeeper prompt (a `.mcpb` is a zip macOS can't staple). `make-icon.py` renders both the
  bundle icon and the panel app icon from one source.

- **UX adoption pass — the panel reads as one calm next action, not an expert cockpit.**
  - *Header decluttered:* four visible actions — **Run unit tests** (the one primary chip),
    **Export**, **AI**, **?** — with DOIs / Library / Retractions / Evidence map / Reload / Theme
    in a **⋯ Tools** dropdown (native `<details>`, no new component).
  - *One-path first run:* **Start your review** (1 add manuscript → 2 extract claims → 3 review
    first claim); screen-a-topic and add-claims collapse behind "I don't have a manuscript yet";
    the wrong-ledger recovery (your work may be in another ledger → one-click Switch) stays prominent.
  - *Legend teaches manuscript-mark STATES* (`[oo]` accepted · `[o]` needs support · `[r]` review
    needed · `[d]` decided · `[u]` untestable · `[··]` pending), separate from the card's decision
    actions — fixing the same-letter, different-meaning confusion.
  - *Conditional stepper:* `Rate → Decide → Write` with no AI, `Rate → AI second opinion → Decide
    → Write` when one exists — so "Reveal" never looks done when nothing was revealed.
  - *Inline notifications* with a **Retry** replace blocking `alert()`s; the server's remediation
    makes them state what happened, why, and the next action. The evidence map leads with
    "Stored on this computer. Nothing uploaded."

- **Release provenance.** Manual `workflow_dispatch` desktop builds now checkout the exact
  `release_tag`, so a `.mcpb` attached to `vX.Y.Z` is built from `vX.Y.Z` — wheel, source archive,
  and desktop extension agree. The Layer-0 **`screen_topic`** prompt is now registered on the MCP
  server and listed in both desktop manifests (Claude Desktop can invoke it), with a test that the
  manifests advertise every server-registered prompt.

## 0.19.0 — evidence confidence tiers, the organized panel, topic screening, the GDPR contributor notice, and the panel app icon (2026-06-18)

- **Organized-panel "X of N support" aggregate (ADR-0008, the review/guideline tier).** Brings
  systematic-review and guideline panels onto the spine as ORCHESTRATION, not new core:
  `support_start` + `support_commit_human` already record one rating per (claim, candidate, rater)
  keyed by `committed_by`. New `claims/panel.py` (`panel_summary` / `claim_panel_summary` /
  `tier_of`) reads them into "how many of N independent human reviewers support a claim", the
  value distribution, raw inter-rater agreement, and the ADR-0008 tier (**1 individual · 2–7
  review · 8+ guideline**). The AI is never a panel member (only human ratings counted, so N is
  never inflated); `overstated` is an overclaim, not support; raters dedup by `committed_by`.
  `tools.support_panel` + CLI `claim-support-panel`. Locked by `tests/test_support_panel.py`.

- **Layer-0 "Screen a topic" button (ADR-0008).** The panel's empty state gains a topic-screening
  entry point: it copies a ready-to-paste `screen_topic` prompt; the assistant then proposes
  candidate claims + nearby candidate evidence (leads, not verdicts) and hands off to
  `run_claim_tests`, where the blinded human-first review takes over. `tools.topic_screen_prompt`
  + `POST /api/topic-screen-prompt`; the panel never calls an AI itself (ADR-0007).

- **ADR-0008 — evidence confidence tiers (the contributor-count ladder).** Fixes the epistemic
  architecture: confidence scales with the count of *independent* assessors of the same claim
  (joined on `claim_text_hash`). Layer 0 screening · 1 individual · 2 review · 3 guideline,
  realized two ways — organized panel ("X of N") and pooled corpus (where the **≥5 floor is the
  individual→review boundary**, so k-anonymity and the epistemic floor coincide).

- **Full GDPR contributor privacy notice + Atlas-contribution disclosure.** `docs/CONTRIBUTOR_PRIVACY.md`
  becomes the complete notice — controller + privacy@vahtian.com, three independent unticked
  opt-ins, what a contribution carries / what you must not contribute, de-identified-not-anonymous,
  recipients + the ≥5 aggregate floor, retention, full "your control", GDPR rights + the Finnish
  supervisory authority, and the purpose/legal-basis. The panel's "Contribute to Atlas" gains a
  matching disclosure block; CiteVahti stays download-only.

- **README: the "reusable evidence map" value proposition** + the business framing dropped from
  `docs/STATUS.md` to match the README's plain "Free beta, local-first".

- **Panel app icon.** The review panel now ships a favicon — the brand `[··]` mark — so the
  browser tab, bookmarks, history, and a desktop install show the CiteVahti icon instead of a
  generic one. `favicon.svg` (vector, matches the header mark) plus a 180×180
  `apple-touch-icon.png` (the `.mcpb` icon's navy style) for the iOS home screen; `make-icon.py`
  now renders both the bundle icon and the panel icon from one source. The static handler serves
  `/favicon.svg`, `/favicon.ico`, and `/apple-touch-icon.png`; `index.html` links them and adds a
  `theme-color`. Both assets ship in the wheel.

## 0.18.0 — stale-bond & contradiction warnings, Word↔claims bridge, submission-packet methods, executable blinded AI rater (2026-06-17)

- **Stale-bond warning — evidence assessments are flagged when the claim text changes.**
  A claim-support rating / final decision is a bond formed against a specific wording; each
  is stamped (once, at first write) with its `claim_text_hash`. When the claim is later
  revised, the current hash no longer matches and the bond is surfaced as **stale** —
  advisory, never auto-invalidated. New `claims/bonds.py` (`claim_bond_status`), a read-only
  `claim_bond_status` agent tool, a claim-level banner + per-candidate tag + an inline ⚠ in
  the panel, and `accept_revision` now records the `from_hash`/`to_hash` transition in the
  audit chain. Locked by `tests/test_claim_bonds.py`.

- **Polarity "may contradict" cue surfaced in the review card.** The engine's polarity
  guard (a contradicting passage is never returned as support) now drives a live, inspectable
  panel hint: `claim_lexical_check` also returns `contradiction` / `polarity_cue` /
  `opposing_quote`, and the card shows a "⚠ may contradict" tag with the negation cue and the
  opposing sentence — shown only after the blind rating, never a verdict.

- **Word → claims handoff — copy a pre-filled `run_claim_tests` prompt.** After importing a
  `.docx`, the import-review modal gains a **Copy claim-tests prompt** button that hands over
  the exact `run_claim_tests` choreography with the imported manuscript already embedded
  (`POST /api/claim-tests-prompt`; `tools.claim_tests_prompt`), closing the .docx → claims
  loop. The panel still never calls an AI itself — it only prepares the prompt to paste.

- **Submission-ready methods statement in the review packet.** The packet now includes
  `methods.md`: the `docs/REPORTING.md` human → AI → adjudication paragraph auto-filled with
  the ledger's real numbers (version, model provenance, blinding order, comparable pairs,
  raw agreement, Cohen's κ). Honest by construction — unpinned provenance and absent
  dual-ratings render as `unset` / `n/a`, never invented. New `report/methods.py`.

- **Interactive blinded fill tool for the claim-check ledger (`validation/claimcheck/fill_ledger.py`).**
  Replaces hand-editing JSONL for step 2 of the measurement workflow: `rater1` / `rater2`
  blinded passes (claim + passage only — never the status, the LLM, or the other rater),
  `adjudicate` (reveals both raters), `status`, and `score`. Validates the relation
  vocabulary, verifies each pair's `record_hash`, atomic rewrite, saves after every answer.
  Locked by `tests/test_fill_ledger.py`.

- **Epistemic Risk Score + the `overstated` verdict (2026-06-16).** A derived, advisory,
  non-compensatory per-manuscript triage score (fatal-floor), plus the `overstated` support
  value for the most common citation-integrity failure — the cited paper supports a *weaker*
  claim than the one made (overclaim).

- **Word in/out — the `.docx` bridge (optional `docx` extra).** Adds **Export Word** (`render_docx`
  builds the report as a .docx — headings, counts table, per-claim sections, scope footer;
  `POST /api/report/docx` writes it under `exports/`) and **Import Word** (`docx_to_markdown`
  converts an uploaded .docx manuscript to Markdown via `POST /api/manuscripts/import-docx`; the
  panel shows the conversion in a review modal, then saves through the existing paste flow so the
  human reviews before it lands). Both behind the `python-docx`-only `docx` extra
  (`pip install 'citevahti[docx]'`) — absent, they raise a clear install hint, like `keyring`. The
  ⎙ Export dialog gains Word + Import buttons. CI now installs `[docx]`; tests skip without it.

- **Export menu (Markdown · PDF · review packet) — bridging to the Word world.** The header
  ⎙ Export button opens a dialog with: **Markdown** (the existing report download), **PDF**
  (the report rendered as a print-ready standalone HTML via the new `render_html`, opened for
  the browser's *Save as PDF* — zero dependencies, fully offline), and a **review packet `.zip`**
  (`POST /api/report/packet` → report Markdown + HTML + the structured `claims.json` evidence/
  audit trail + a README) for a supervisor or journal. All local; nothing transmitted. Word
  export + Word import follow in a small optional-`docx`-extra change. Locked by
  `tests/test_report_export.py`.

- **Panel: "✦ Get AI second opinion" on the decide step.** When the reveal shows no AI rating yet,
  a button runs CiteVahti's configured local/external model (`POST /api/ratings/{id}/run-ai`) and
  reloads — the standalone trigger for the executable path, no CLI needed. Off-mode points to ✦ AI
  instead of dead-ending; the MCP assistant path is unchanged. UI only (app.js / styles.css).

- **CiteVahti now runs its own blinded claim-support second opinion (local / api).** The settings
  were configurable; this makes the standalone path *execute*. New `HttpClaimSupportRater` (blinded,
  reuses the shared `chat_completion` transport + `resolve_ai_connection` connection rules) and
  `build_support_ai_rater(config)`; `tools.support_run_ai` builds the rater from config when none is
  injected (off → a clear "AI is off — use local/api or your MCP assistant" error). New route
  `POST /api/ratings/{id}/run-ai` records the AI rating **blind** (the view hides it until a human
  rating exists). The rater abstains rather than emit an out-of-vocabulary value (`overstated`
  included). The MCP assistant path (`submit_ai_support_rating`) is unchanged — this is purely the
  no-assistant fallback. The GRADE `build_ai_rater` was refactored onto the same shared helpers (no
  behaviour change; #59 tests still green). Locked by `tests/test_support_ai_rater.py` + panel
  route tests.

- **Panel AI settings (✦ AI) — MCP-first, all modes selectable.** A panel modal to configure the
  AI second opinion. Leads with the truth that **most users need no setup**: when you drive
  CiteVahti through an assistant over MCP (Cowork / Claude), it already submits the blinded second
  opinion (`submit_ai_support_rating`) — paid by your assistant subscription. The selectable modes
  govern CiteVahti's *own* call: **Off** (human-only / MCP), **Local AI** (Ollama — a model picker
  populated from `ollama list`, Qwen-first, with the digest auto-pinned to `ai_provenance` for
  audit; the workhorse for high-volume screening), **My API key** (external provider; the key lives
  in the keychain/env and is **never entered in or sent through the panel** — only its presence is
  shown). New routes `GET/POST /api/ai-config` and `GET /api/ai/local-models`. "You rate first —
  the AI is a blinded second opinion" throughout. Route tests in `tests/test_panel_api.py`;
  verified end-to-end against a live panel + local Ollama.

- **Real AI rater backend — three modes (Off · Local AI · My API key), privacy-first.** The
  `AiRater` seam shipped only a `FakeAiRater`; now there is a real, optional, **blinded**
  `HttpAiRater` over an OpenAI-compatible or Anthropic chat endpoint, plus `build_ai_rater(config)`
  that returns it or `None` when AI is off. New `ai_connection` config block: **off** (human-only),
  **local** (a model on your device/network — Ollama / LM Studio, **no API key**, localhost/https
  only, nothing leaves the device), **api** (external provider with your own key from the credential
  store — env escape hatch honored, **https-only so a key never rides plaintext**). New
  `AI_API_KEY` secret (`CITEVAHTI_AI_API_KEY`). The rater stays blind (the `rate` signature
  excludes the human value) and **abstains rather than fabricate** an out-of-scheme value; the model
  is still pinned in `ai_provenance` for audit. Ports MatchVahti's AI-settings concept to
  CiteVahti's rater architecture. Locked by `tests/test_ai_rater.py` (offline, fake poster). The
  panel settings UI is a follow-up.

- **claim-check measurement ledger (`validation/claimcheck/`).** The "measure before you
  tune" half of the polarity work: a pre-registered (claim, passage) ledger scored κ-first,
  with support- and contradiction-detectors measured against two-rater human gold and an LLM
  advisor scored against the same gold (correlated-error count shown). `build_ledger.py` seeds
  from the repo's real `text.py`; `score_ledger.py` refuses to invent labels; a synthetic demo
  shows the output shape (cite no number from it). Mirrors MatchVahti's validation protocol.
- **`keyring` test hygiene.** The optional `keyring` extra is now `pytest.importorskip`-guarded
  in `test_keyring_graceful.py` and `test_credentials.py`, so the suite is green without the
  extra installed (it ran the keyring path only when present; now it skips cleanly otherwise).
  No behavior change — `keyring` stays the optional, secure OS-vault store with the env-var
  escape hatch and never-on-disk guarantee.

- **claim-check polarity guard — a contradicting source is never silently returned as
  support (correctness fix).** Lexical `coverage_score` is direction-blind: *"Drug X did not
  reduce mortality"* shares its content tokens with *"Drug X reduced mortality"*, so a
  contradicting passage scored as high as a supporting one and was returned
  `supported_candidate`. New deterministic (no-AI) `has_negation` / `polarity_conflict` in
  `retrieval/text.py` route a high-overlap but opposite-polarity passage to a new
  `contradiction_candidate` status (the mirror of `supported_candidate`; still a *candidate*,
  never asserts truth). The aggregate leads with the contradiction and `check` adds a
  conflicting-evidence warning. Two improvements over the seed patch: **(1)** the flag is
  *inspectable* — `negation_cue` / the new `PerCitekeyResult.polarity_cue` name the word that
  flipped the polarity (e.g. `"did not"`), mirroring MatchVahti's "Flagged on the word …"
  pattern; **(2)** a source carrying **both** a supporting and an opposing passage surfaces the
  conflict (both passages + cue + warning) instead of silently dropping the opposing one.
  Conservative by design (fires only on lexical overlap + opposite negation parity);
  paraphrase / synonymy stay the advisory layer's job. Locked by `tests/test_claimcheck_polarity.py`.

## 0.16.0 — verified→accepted (BREAKING), [u] untestable, report provenance, --json, desktop extension (2026-06-12)
## 0.17.0 — unit-test the manuscript, edit claims inline, the Atlas contribution + FullVahti write-back (2026-06-16)

The release that makes CiteVahti's core metaphor literal and connects the tool to its
siblings. Everything below is local-first and opt-in; nothing new leaves the machine
without an explicit, previewed action.

- **"Run unit tests" on the manuscript.** Each claim is a test case. `citevahti test`
  (and a **▶ Run unit tests** panel button) reports pass / fail / skip per claim — does
  the claim meet its references, and are the citations real? Offline by default
  (has-evidence, reviewed, supported, identifiable citation); `--online` also verifies
  the citation resolves and isn't retracted. The CLI exits non-zero on failure, so it can
  gate CI on a manuscript repo.
- **Edit the claim while reviewing evidence.** A first-class **✏ Edit claim** action on
  the review card, in any phase — reword an overstated claim as you read the evidence.
  Writes to the manuscript `.md` (previewed, backed-up, undoable) when the document is
  open; otherwise records an audited revision in the ledger.
- **Researcher-friendly panel.** A folder picker (no path typing), a one-click **Save to
  Zotero** on search results, openable **DOI links** and inline **abstracts**, a clearer
  fit-check (P/I/O/Claim with a 0/1/2 scale), a keyboard-shortcut legend with an off
  toggle, a printable audit report, and plain language throughout (no more "bind/unbound").
  Claim spans are keyboard-activatable (Enter/Space).
- **Shared claim-text normalization (spec v1).** `claim_text_hash` is now computed over a
  normalized claim (NFC → lowercase → collapse whitespace → trim), **byte-identical across
  CiteVahti, MatchVahti, and the corpus** — so the same claim pools into one AtlasVahti
  cell. See [`docs/CLAIM_NORMALIZATION.md`](docs/CLAIM_NORMALIZATION.md).
- **Warehouse + Atlas contribution (download-only).** The de-identified warehouse is now
  visible in the panel (status, opt-in, export, purge), and a **Contribute to Atlas** flow
  builds a consented, de-identified bundle you can **download** — de-identification is
  enforced (`assert_poolable` refuses any leak), nothing is uploaded, and every
  contribution is revocable and audited.
- **CiteVahti → FullVahti tag write-back.** The `local_addon` write backend now writes
  status tags into Zotero through the [FullVahti](https://github.com/heidihelena/fullvahti)
  plugin's token-gated door (`/fullvahti/tag`); `citevahti status` probes the door and says
  whether it's reachable + enabled. The token is local-only.
- **Fixes:** forward-compatible candidate loading (a newer-written ledger no longer crashes
  an older reader and takes down the whole review surface); online unit-test-check failures
  are surfaced loudly instead of read as green; the inline claim-revise is guarded; the
  legacy dashboard mockup is watermarked as non-production.

## 0.16.0 — guided run, panel wizard, opt-in timestamping; verified→accepted (BREAKING) (2026-06-16)

Highlights since `v0.16.0-beta.1`:

- **One guided command: `citevahti run`** (init if needed → say what's next → open the
  panel), plus **`citevahti resume`** and **`citevahti doctor`** (plain-language readiness).
  A single shared next-action resolver (`citevahti.workflow`) now backs every surface, so
  the panel, VS Code, CLI, and agent prompt no longer each re-derive the
  `rate → reveal → decide → write` phase.
- **Panel "what's next" wizard**: a banner that names the one next action and routes you to
  it — the no-terminal path for new users.
- **Opt-in cryptographic timestamping of the audit head** (RFC 3161; `citevahti timestamp`)
  — the foundation for third-party-verifiable provenance. Off by default; only the SHA-256
  audit-head hash ever leaves the machine. Full TSA certificate-chain validation is a
  follow-up, so RFC 3161 trust is currently experimental.
- **Citation-on-copy**: copying a cited passage in the panel carries its source reference
  (plain text + HTML). **Timestamped report** download button (header **⎙ Report**).
- **`citevahti vocabulary`** exposes the verdicts/states/phases as JSON; the VS Code
  extension reads it instead of hardcoding the verdict map.
- Panel now **defaults to light** and remembers the theme toggle.
- **Fix:** the report and panel select a (claim, candidate)'s rating deterministically
  (most-advanced / most-recent), not an arbitrary uuid-sorted one.
- **CI** runs the offline suite (py3.10 + 3.12) and the VS Code compile on every push/PR;
  PEP 639 license metadata; SECURITY.md / REVIEW_CHECKLIST / VS Code docs de-drifted.

Earlier in 0.16.0 (the `v0.16.0-beta.1` line):

- **BREAKING: the `[oo]` claim state is renamed `verified` → `accepted`**
  (external-audit finding #7-B). "Verified" implied clinical/scientific truth;
  the state means "has an accepted, supporting citation". The short codes
  (`oo/o/r/d`) are unchanged, so keyboard flows and the panel are unaffected.
  Consumers of `claim-report --json` / `start --json` must read
  `counts.accepted` and `state: "accepted"` instead of `"verified"`. Nothing
  in the ledger itself stored the old name (states are derived at report
  time), so no data migration is needed — only JSON consumers change.
- **New `[u] untestable` claim state** for sources outside the indexed
  literature (books, chapters, grey literature): mark with
  `citevahti claim-untestable <id> --reason "…"`. Reported as its own block,
  never counted as "needs attention".
- **Citation-Integrity Report now carries its own provenance**: audit-chain
  head hash + entry count + intactness, the full-ledger claim denominator
  (subset reports are visibly subsets), per-candidate retraction flags, and a
  Scope & limitations footer (tamper-evident-not-signed caveat included).
- `retraction_scan` (panel) now logs a `retraction.scan` audit event; the
  report cites the last scan timestamp.
- Panel Zotero search now includes group libraries (`library="all"`).
- New `docs/REPORTING.md`: fill-in-the-blanks methods paragraph wired to
  `agreement-report`.
- **New agent tool `open_review_panel`** (+ `start.launch_panel()`): the agent
  can bring up the human's loopback rating panel at the rate-first step, which
  closes the desktop-extension (.mcpb) no-terminal dead-end. The
  `run_claim_tests` prompt now points at it. Desktop-extension scaffold
  (manifests, build + sign/notarize scripts) merged; README/QUICKSTART now
  surface the no-terminal install above the pip route.
- `--json` across the claim spine (claim-add/list/untestable, candidate-list,
  claim-support-*, claim-decide, decision-list) + `docs/CI.md` pre-commit and
  GitHub Action recipes.

## 0.15.0 — Panel UX hardening + beta notice: error codes, legend, accessibility, write-target disclosure, paste hand-off, bounded backups (2026-06-07)

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
- **feat(panel): beta / pricing notice.** A `BETA` badge in the header, a note in the
  legend, and a banner on the first-run screen state that CiteVahti is in beta and free
  to use, that pricing for hosted/advanced features may come later, and that a free
  local/community version is intended to remain available. A test asserts the notice
  ships in the served page.
- **feat(panel): claim deep-links.** `?focus=<claim_id>` opens that claim's card on
  load and `?legend=1` opens the legend — handy for sharing a specific review and for
  reproducible screenshots.
- **docs: onboarding screenshots + a synthetic demo ledger.** `docs/demo/build_demo_ledger.py`
  builds a small, fully invented ledger (no real manuscript or citations) that drives the
  real engine, so `docs/screenshots/*` show genuine claim states. README now opens with a
  "See it" gallery and the beta notice.

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
