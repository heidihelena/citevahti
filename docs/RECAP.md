# CiteVahti — status & recent work

A short standing note: what was recently shipped, where the project stands, and
what's next.

## The one-line product

**CiteVahti runs unit tests on manuscript claims.** The manuscript is the code,
each claim is a test, and CiteVahti checks the evidence before you cite — the human
rates support first, the AI second opinion stays blinded until then, and Zotero
writes are previewed, confirmed, and undoable.

## Recent releases (0.8 → 0.12)

- **0.8.0** — richer VS Code inline evidence card (PICO fit, citation-fit score,
  excerpt); "Change reference" search-and-link.
- **0.9.0** — two co-primary surfaces (ADR-0007): a chat client via the MCP server,
  and a loopback **side panel** as the blind human decision surface (MCP prompt,
  panel + thin loopback HTTP API, audit-log inter-process lock).
- **0.10.0** — the **claim-test frame**: the canonical `run_claim_tests` MCP prompt,
  a stable finding-label + state vocabulary, and the **Claim Test Report**
  (`citevahti report`).
- **0.11.0 / 0.11.1** — one command, **`citevahti start`** (panel + browser + MCP in
  one process; doubles as the chat client's MCP config line), plus hardening: a busy
  port is health-probed before reuse, loopback enforced inside `start()`.
- **0.12.0** — **rate-first** in the VS Code card: the Accept/Caution/Review/Reject
  verdict is locked until you record your blind support rating (keys 1–6), mirroring
  the side panel. CLI + extension aligned to one version number.

## Where we are

- 544 offline tests green; the extension compiles clean; smoke (probe +
  verify-audit) OK.
- Engine + safety invariants stable — blinding, decision-gated/undoable writes,
  hash-chained audit, no raw Zotero write, no agent final decision.
- Published on PyPI through **0.12.0** (CLI + extension on one version number).
- Honest status: a strong **researcher preview**, not yet friction-free for ordinary
  academics.

## Where we're heading (next, roughly in order)

1. **"Current citation" as a first-class field** — *paused, not dropped.* The report
   shows candidates, not the manuscript's originally-cited reference;
   reference-integrity findings (`reference_broken` / `reference_hallucinated`) are
   agent-produced, not stored. Open design fork: store a deterministic resolve fact
   only (no stored AI judgment) vs store agent findings (own ADR).
2. **Clearer provenance language + tighter rationale capture** (researcher ask).
3. **Deferred, own ADRs:** `LLMProvider` (free tier). A full web editor and a remote
   (Streamable-HTTP) transport would be a possible future hosted layer (ADR-0003),
   not part of the free local tool.

## Maintainer note

Design priority: keep the shape — claim-as-test, human-first, blinded, auditable —
and keep cutting friction rather than adding surface.
