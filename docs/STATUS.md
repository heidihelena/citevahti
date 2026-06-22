# CiteVahti — status & capabilities

*The detailed status, positioning, and full capability surface. The README keeps the
short version; this is the depth behind it.*

> *A product of **Vahtian**.*

## Status: v0.21.5 — cite-stable export, group libraries, and a zero-setup demo

The ADR-0001 evidence-decision ledger is complete end to end (claim → candidate →
blinded support rating → final decision → decision-gated, undoable Zotero write →
de-identified warehouse), hash-chain audited, with 800+ offline tests. New in 0.21.0:
**cite-stable export** (durable `[@citekey]` + `references.bib` → Word via Pandoc,
preferring your own Better BibTeX keys), **safe group-library** writes/dedupe, and a
zero-setup **`citevahti demo`** (synthetic ledger + panel, no Zotero/AI/network). The
loopback panel is the **inline manuscript reviewer**: claims highlighted in place, an
action-first **Rate → Reveal → Decide → Write** card, and enough built in to run the
whole loop without the chat — find evidence (PubMed / OpenAlex / Semantic Scholar /
your Zotero library), add claims, connect Zotero (paste or OAuth), backfill DOIs, scan
for retractions, open a reference's PDF in Zotero, revise the `.md`, and read a per-claim
audit trail. The AI second rating can come from your MCP assistant (Claude Desktop / ChatGPT /
Codex), a local model (Ollama / LM Studio), or your own API key — and every mode stays blinded
until your human rating exists.

**`citevahti start`** launches the whole workspace at once — panel + browser + MCP
server — and doubles as the one line in your chat client's MCP config. You drive the
blinded review from **two co-primary surfaces (ADR-0007)**: a **chat client** (Claude
Desktop / ChatGPT / Claude Code / Codex) via the MCP server and its **`run_claim_tests`**
prompt, and a **loopback side panel** (`citevahti-panel`) that is the blind human-rating
surface — the AI rating stays hidden until you rate.

The VS Code inline review loop remains one adapter: claim spans by state, an evidence
card that is **rate-first** (the Accept/Caution/Review/Reject verdict is locked until you
record your blind support rating), with **PICO fit-checks, a citation-fit score, and the
supporting excerpt**, a **"Change reference"** PubMed search-and-link flow, an editor-mode
Citation-Integrity Report, and an agent-proposes / human-accepts revision diff.

Local-first and single-user. Your manuscript text and ratings stay on your machine and
there is no telemetry; the only outbound calls are to the literature services it searches
or checks — **PubMed (NCBI), OpenAlex, Semantic Scholar, and Crossref/doi.org** — and, if
you connect it, **your Zotero**. Search queries and the titles/DOIs/PMIDs of references
you look up are sent to those services. (PubMed is the primary search source; "PubMed-only"
was an earlier, narrower scope.)

## Positioning

CiteVahti is free, local-first, and built for researchers who cite: it checks whether each
manuscript claim is actually supported by the paper cited for it, with a blinded,
human-first rating workflow and an auditable local ledger.

## Run unit tests on your manuscript

The manuscript is the code; each scientific claim is a test case. CiteVahti checks whether
each claim is actually supported by its cited or candidate evidence — using PubMed and
Zotero, a **blinded, human-first** rating workflow, and MCP-connected agents such as Codex
or Claude Code. The human rates support first; the AI second opinion stays hidden until
then; Zotero writes are previewed, confirmed, and undoable.

Three doors to the same product: *run unit tests on your manuscript* (agents / technical
researchers) · *check every claim before you cite it* (researchers) · *create an auditable
claim-evidence trail* (journals / institutions). The core unit is **not a paper and not a
reference — it is a claim test.** VS Code is one adapter and PyPI one install path; neither
defines the product. CiteVahti's value is **not** autonomous reviewing; it is a documented
**human → AI → adjudication** workflow you can report transparently in a methods section —
[REPORTING.md](REPORTING.md) has the fill-in-the-blanks methods paragraph and the commands
that produce its numbers.

The de-identified validation warehouse is local too; contributing any of it to the shared
evidence corpus is a separate, active opt-in with its own
[contributor privacy notice](CONTRIBUTOR_PRIVACY.md) — never automatic.

> **The human or panel is always the decider. The AI is a blinded, advisory second rater
> only. AI values are advisory, never decisive, and never silently propagated.**

## Beta

CiteVahti is in beta and free to use. Local-first: your manuscript and ratings stay on your
device unless you choose to use an external AI model.

## Direction: the citation-integrity ledger (ADR-0001)

As of 0.4.0 the product spine is **citation integrity** — *verify the claim before you
cite it.* The **claim** is the first-class object, and the ledger is:

```
manuscript claim → candidate papers → blinded claim-support rating
  → human-owned final decision → decision-gated, undoable Zotero write → audit
```

An **audited** Zotero write happens only as the terminal step of that chain (one claim ·
one paper · one final `accept` decision · provenance · transaction · audit · undo) — never
silently, never for a paper that doesn't support the claim. See
[adr/0001-citation-integrity-architecture.md](adr/0001-citation-integrity-architecture.md)
for the decision and the local-first build sequence (**steps 1–6 complete**), and
[adr/0002-ui-delivery-and-review-layer.md](adr/0002-ui-delivery-and-review-layer.md) for
the inline `[oo/o/r/d]` review-layer UI direction.
