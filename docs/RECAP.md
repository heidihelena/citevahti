# Where CiteVahti is — recap (2026-06-06)

A short standing note: what we just shipped, where we are, what's next. Update it
at the end of a working session.

## The one-line product

**CiteVahti runs unit tests on manuscript claims.** The manuscript is the code,
each claim is a test, CiteVahti checks the evidence before you cite — human rates
first, AI second opinion stays blinded until then, Zotero writes are previewed,
confirmed, and undoable.

## What we did this week (0.8 → 0.10)

- **0.8.0** — full rename to `citevahti`; richer VS Code inline evidence card
  (PICO fit, citation-fit score, excerpt); "Change reference" search-and-link.
- **0.9.0** — got off the IDE. **Two co-primary surfaces (ADR-0007):** a chat
  client via the MCP server, and a loopback **side panel** as the blind human
  decision surface. Added the MCP prompt, the panel + thin HTTP API, abstract +
  PICO wiring, and an audit-log inter-process lock.
- **0.10.0 (today)** — the **claim-test frame**. Canonical `run_claim_tests` MCP
  prompt; stable finding-label + state vocabulary; the **Claim Test Report**
  (`citevahti report`); README reframed; `docs/workflows/` added. Folded in the
  external 0.9.0 review fixes (connection-status dot, stale-write reset, required
  rationale, loopback enforcement, wording, package-lock).

## Where we are

- 544 offline tests green; extension compiles clean; smoke (probe + verify-audit) OK.
- Engine + safety invariants unchanged since 0.8 — blinding, decision-gated/undoable
  writes, hash-chained audit, no raw Zotero write, no agent final decision.
- Published: PyPI through **0.12.0** (CLI + extension on one version number).
- Honest status: a strong **researcher preview**, not yet friction-free for ordinary
  academics (the reviewers are right).

## Where we're heading (next, roughly in order)

1. ~~**One command: `citevahti start`**~~ — **done (2026-06-06).** `citevahti
   start` launches the panel + browser in a background thread and serves MCP over
   stdio in the foreground; it doubles as the one line in the chat client's MCP
   config. Plain next-step prompts ("Open Zotero", "Choose a manuscript") go to
   stderr (stdout is the MCP channel); degrades to panel-only if the `mcp` extra
   is absent. See `src/citevahti/start.py`, `tests/test_start.py`,
   `docs/CHAT_AND_PANEL.md` §2. **Released as 0.11.0**, then **0.11.1** folded in
   the external review fixes: a busy port is now health-probed before reuse
   (foreign occupant → fail loudly), loopback is enforced inside `start()`, the VS
   Code extension version was aligned (was stuck at 0.10.0), and the README/
   QUICKSTART/chat docs were de-staled (PyPI install, test counts, `run_claim_tests`).
2. ~~**VS Code inliner: rate-first gating**~~ — **released as 0.12.0 (2026-06-06).**
   The inline card now shows the blind support-rating buttons first (keys 1–6) and
   keeps the Accept/Caution/Review/Reject verdict (+ `o/o/r/d` keys) locked until a
   human support rating is committed — mirroring the side panel. Extension-only
   (`vscode-extension/src/extension.ts`); the support-rating CLI commands already
   existed. CLI + extension aligned to one version number.
3. **"Current citation" as a first-class field** — *paused (2026-06-06) pending
   product-line sequencing,* not dropped. The report shows candidates, not the
   manuscript's originally-cited reference; reference-integrity findings
   (`reference_broken`/`reference_hallucinated`) are agent-produced, not stored.
   Open fork: store a deterministic resolve fact only (no stored AI judgment) vs
   store agent findings (own ADR).
4. **Clearer provenance language + tighter rationale capture** (researcher ask).
5. **Deferred, own ADRs:** `LLMProvider` (free tier); the full web editor +
   Streamable-HTTP transport are the **paid hosted tier** (ADR-0003), not this one.

## Maintainer note

Design priority: keep the shape — claim-as-test, human-first, blinded, auditable —
and keep cutting friction rather than adding surface.
