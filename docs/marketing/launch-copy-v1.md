# CiteVahti — production launch copy (v1, repo-checked)

<!-- content-pipeline header -->

- **Audience:** systematic reviewers, PhD supervisors, journal editors, research support offices — anyone accountable for citation accuracy in a manuscript.
- **Decision problem:** "Can I trust that every citation in this document says what the text claims it says — before a reviewer or reader finds out it doesn't?"
- **Funnel stage fed:** Awareness → free tool (local app) → Kit / design-review.
- **Evidence basis:** product architecture facts from CiteVahti development (local-first Zotero MCP; dual-rating adjudication that mirrors the dual-screening logic of systematic reviews, with PRISMA-trAIce / RAISE-*style* transparency reporting). The quotation-error figure is sourced (see the problem section); every product claim below was checked against the repo — see the resolution log at the end.
- **CTA (one):** Run the app on a real reference list. <!-- swap to beta-signup link if a hosted try-page ever exists; today the app is local -->
- **Risk flag:** Not clinical content. Low risk. One integrity-claim risk: never let copy imply CiteVahti *guarantees* citation correctness — it surfaces problems for human adjudication. Before this copy goes anywhere public, run it through the `citevahti-claims` skill.

-----

## Hero

**Every citation, checked. No verdicts, just evidence.**

CiteVahti checks every claim–citation pair in your manuscript and shows you which citations hold up, which need a closer look, and which don't support the claim they're attached to — with the reasoning in view, so you fix them before a reviewer does.

## The problem (evidence section)

Citation errors are not rare edge cases. In a systematic review and meta-analysis of 28 studies, the pooled **total quotation-error rate was 25.4%** (95% CI 19.5–32.4) — roughly one cited claim in four — including a **major-error rate of 11.9%** (95% CI 8.4–16.6), the kind that misrepresents what the cited source actually found. Even the lowest study estimate, 6.7%, is far from negligible (Jergas & Baethge, 2015, *PeerJ* 3:e1364). Retracted papers keep accumulating citations years after retraction. And AI-assisted writing has added a new failure mode: fluent, well-formatted references to papers that don't exist.

Most reference managers check formatting. None of that tells you whether the citation actually supports the sentence it's attached to.

## How it works (product facts)

1. **Connect your library.** CiteVahti runs against your Zotero library, locally. Your manuscript text and ratings stay on your machine — no telemetry, nothing uploaded to us. (Literature lookups do go out, to PubMed, OpenAlex, Semantic Scholar and Crossref — the same indexes a reviewer would check.)
1. **Check every claim–citation pair.** You rate each citation first; a blinded AI second rating is revealed only after yours is in, and disagreements are routed to explicit adjudication — the dual-screening logic of a systematic review, with PRISMA-trAIce / RAISE-*style* transparency reporting.
1. **Record an evidence-tiered decision.** Every claim–citation pair gets a state *you* record — **accepted / caution / review / rejected**, plus **untestable** for anything outside the indexed literature — with **retraction and claim–source-mismatch flags** surfaced along the way. The reasoning is shown, not hidden.

Available as an MCP server (Claude Desktop, Claude Code, other MCP clients), a desktop extension (`.mcpb`), a VS Code extension, and a local web app (the loopback review panel — it runs on your machine, not ours).

## What CiteVahti will not do (boundary section — keep verbatim)

CiteVahti never issues a verdict on your work. It does not "approve" a manuscript, certify integrity, or replace your judgment as author or reviewer. It surfaces evidence about each citation and shows its reasoning. Adjudication is yours. It also never phones your data home: the architecture is local-first by design.

## Beta honesty block (keep until production criteria met)

CiteVahti is in beta. That means: the checking pipeline works, the failure modes are documented openly, and we **will publish our evaluation results** — precision and recall against a ground-truth citation set — rather than asking you to take accuracy on faith. The measurement protocol is pre-registered in the repo (`validation/claimcheck/`); no benchmark numbers are published yet, and we say so plainly until they are. [Link the eval-results page here once `citevahti-eval` produces it.]

## CTA

**Run it on one reference list.** Ten minutes, your own manuscript, on your own machine. → [install / quickstart link — `docs/QUICKSTART.md`]

-----

## LinkedIn excerpts (log per content-pipeline)

1. "Your reference manager checks formatting. Nothing checks whether the citation supports the sentence." → thread on quotation errors (pooled total error rate 25.4%, 95% CI 19.5–32.4; Jergas & Baethge 2015) + local-app CTA.
1. "We will publish CiteVahti's precision and recall instead of asking you to trust it. Evidence tools should be held to evidence standards." → eval-results post, **once numbers exist** (until then this stays a commitment, not a boast).
1. "CiteVahti never issues a verdict. Here's why that's a feature, not a limitation." → brand-core piece.

-----

# Resolution log (draft v1 → repo-checked v1)

Each item below was a `[VERIFY]` flag or a claim that contradicted the build in the first
draft. This log records how it was resolved, so the copy carries its own provenance —
fitting, for a citation-integrity tool. **`citevahti-claims` still runs on the final copy
before any public use;** this log is the source trail, not a substitute for that audit.

1. **Tier labels — FIXED.** The draft's invented "verified / contested / unverifiable /
   flagged" is replaced with the shipped vocabulary: **accepted / caution / review /
   rejected** (from `[oo]`/`[o]`/`[r]`/`[d]`) plus **untestable** (`[u]`), with retraction
   and mismatch flags named separately (`skills/citevahti-dev/SKILL.md`, `docs/GLOSSARY.md`).
   "Verified" — the certification-adjacent word the risk flag warns about — is gone, and
   the state is now explicitly one *you record*, not one the tool issues.

2. **"PRISMA-trAIce / Cochrane aligned" — FIXED.** Softened everywhere to *"mirrors the
   dual-screening logic of systematic reviews, with PRISMA-trAIce / RAISE-style
   transparency reporting."* This matches `docs/METHODS.md`, which explicitly disclaims
   compliance with or endorsement by PRISMA 2020, PRISMA-trAIce, RAISE, or any framework.
   The Cochrane/Campbell name-drop is dropped.

3. **"Web app" implying hosted — FIXED.** The app is the local loopback panel (ADR-0007);
   there is no hosted try-it page. Copy now says "local web app… runs on your machine, not
   ours", the CTA points at install/quickstart, and step 1 states precisely what stays
   local (manuscript + ratings; no telemetry) versus what goes out (literature lookups).

4. **Quotation-error rate — FIXED (sourced, then corrected to the pooled estimates).**
   Cited to Jergas & Baethge (2015), "Quotation accuracy in medical journal articles — a
   systematic review and meta-analysis," *PeerJ* 3:e1364, DOI 10.7717/peerj.1364 (PMID
   26528420). The copy uses the paper's **meta-analytic pooled estimates** (28 studies
   included, of 559 screened): total **25.4%** [95% CI 19.5–32.4], major **11.9%**
   [8.4–16.6], minor **11.5%** [8.3–15.7], lowest total estimate 6.7%. An earlier revision
   mistakenly used the medians of the raw per-study ranges (22.5% total) and mis-stated the
   major/minor figures — itself a quotation error, corrected here against the source
   abstract. The lesson is on-brand: a sourced-looking number can still be wrong; check it
   against the source, which is the whole point of the tool. (A newer 2025 meta-analysis in
   *Research Integrity and Peer Review* exists if a refresh is wanted later.)

5. **Eval-results promise — FIXED (tense).** The beta block now says "we **will** publish"
   and states outright that no benchmark numbers exist yet, pointing at the pre-registered
   protocol in `validation/claimcheck/` and its committed acceptance thresholds. Consistent
   with `docs/KNOWN_LIMITATIONS.md`. Swap in the eval-results link once `citevahti-eval`
   scores a filled ledger.

6. **Fabricated-reference scope — STANDING CAUTION (unchanged).** The anti-fabrication
   guarantee is on the *write* path (no citekey without Better BibTeX; no Zotero write
   without a DOI/PMID). Detecting fabricated references in an *incoming* list is the
   `citevahti-screen` DOI/PMID sweep — items with neither identifier can't be
   machine-checked (`docs/KNOWN_LIMITATIONS.md`). The hero copy stays within this; never
   let later copy escalate to "catches hallucinated references" (must-not-claim list).
