---
name: citevahti-claims
description: Use before publishing ANY public CiteVahti artifact — site copy, README, LinkedIn post, release notes, docs, conference slide, screenshot caption — to audit it against the must-not-claim list and the evidence-tier language rules. Also use when drafting such copy, or when asked "can we say this about CiteVahti?". Protects the brand core - CiteVahti surfaces evidence for human adjudication and never certifies, guarantees, or issues verdicts.
---

# CiteVahti claims — audit public language before it ships

CiteVahti's brand core is a *refusal*: it never issues a verdict, and it holds itself to
the evidence standards it promotes. One sentence of overclaiming — "AI-verified",
"guarantees accuracy", both forbidden below — spends that credibility permanently. This
skill audits every public artifact against the boundary the product actually keeps.

Canonical sources (the audit is against these, not memory):
`docs/DISCLOSURE.md` (what is never certified) · `docs/KNOWN_LIMITATIONS.md` (what is
honestly not done) · `docs/METHODS.md` §PRISMA-trAIce (framework-compliance ceiling) ·
`docs/SAFETY_INVARIANTS.md` (what "safe" concretely means).

## Triggers

**Use when:** publishing or editing site copy, README, `docs/STATUS.md` positioning,
LinkedIn/social posts, release notes, talk slides, marketing drafts
(`docs/marketing/`), or answering "can we claim X?".

**Do NOT use for:** internal notes and ADRs (not public), or code review.

## The must-not-claim list

Reject or rewrite any artifact that states or *implies*:

| Forbidden | Why | Say instead |
|---|---|---|
| "guarantees accuracy / correctness" | no accuracy promise can be made; recall < 100% is a documented product fact | "surfaces problems for human adjudication" |
| "AI-verified" / "verified by AI" | AI is a blinded advisory second rater; it never sets the final value | "human-decided, AI-assisted, blinded second opinion" |
| "catches all errors" / "no citation problem escapes" | detection is imperfect and DOI/PMID-keyed; untestable claims exist | "flags what it can check; marks the rest untestable" |
| certification language: "certifies", "approves", "CiteVahti-validated", badges/seals | DISCLOSURE.md: use does not certify truth, quality, or absence of problems | "structured decision support and an audit trail" |
| "PRISMA / PRISMA-trAIce / Cochrane compliant, endorsed, aligned" | METHODS.md explicitly disclaims compliance and endorsement | "mirrors dual-screening logic; PRISMA-trAIce / RAISE-*style* transparency reporting" |
| verdict language: "CiteVahti says this citation is wrong" | it records *your* judgment with provenance | "flagged for your review", "did not find support" |
| accuracy numbers with no source | until the eval ledger is scored, there are no numbers (KNOWN_LIMITATIONS.md) | cite the published eval page, or phrase as commitment ("we will publish…") |
| "your data never leaves your machine" (absolute) | literature lookups go to PubMed/OpenAlex/Semantic Scholar/Crossref | "manuscript and ratings stay local; only literature queries go out; no telemetry" |
| "catches hallucinated references" (absolute) | fabricated-reference detection keys on DOI/PMID; identifier-less items can't be checked | "refuses to write unverifiable citations; flags references that don't resolve" |
| hosted-service implications: "upload", "try it in your browser" for the panel | ADR-0007: the web app is a local loopback panel; nothing is hosted | "runs locally; ten-minute install" |

Test for *implication*, not just literal strings: a padlock badge, a "100%" visual, a
checkmark labelled "verified" — not allowed — or a testimonial saying "CiteVahti
approved my manuscript": none of these pass the audit, even with clean body text.

## Required language (presence check)

Public artifacts that describe what CiteVahti does must keep, in substance:

1. **Human adjudication owns the outcome.** The human is always the decider; the AI is a
   blinded advisory second rater.
2. **Evidence-tier vocabulary matches the build.** Claim states are accepted `[oo]` /
   caution `[o]` / review `[r]` / rejected `[d]` / untestable `[u]` — don't invent a
   parallel public vocabulary. The launch-copy draft's invented tier names failed
   exactly this; see the repo-check notes in `docs/marketing/launch-copy-v1.md`.
3. **Local-first, stated precisely** (local manuscript + ratings, outbound literature
   lookups, no telemetry).
4. **Beta honesty** while in beta: limitations documented, no published benchmark until
   `citevahti-eval` publishes one.
5. **The boundary section survives editing.** Any long-form artifact keeps a "what it
   will not do" statement equivalent to DISCLOSURE.md — editors love cutting it; don't.

## Audit procedure

1. Read the artifact end to end, including alt text, captions, image content, and CTAs.
2. Sweep the must-not list — literal terms first (grep for: guarantee, verified,
   certif, approve, compliant, aligned, catches all, 100%, upload), then implications.
3. Run the presence check (five required items above, where the artifact's length warrants).
4. Check every factual product claim against the current repo (features, test counts,
   version, surfaces) — copy rots; `docs/STATUS.md` is the source for positioning facts.
5. Anything marked `[VERIFY]` blocks publication until resolved — no exceptions.
6. Return a verdict per finding: **rewrite** (with proposed wording), **cut**, or
   **cleared**, each with the doc it was checked against.

## Hard rules

- **NEVER clear an artifact with an unresolved `[VERIFY]` flag.**
- **NEVER approve certification or verdict language** — no exceptions for "it's just a
  LinkedIn post"; social copy is where it leaks first.
- **NEVER quote an accuracy number that isn't on the published eval page.**
- **NEVER let this skill's own output overclaim** — findings are advisory to the
  maintainer, who decides. (The brand rule applies to the brand police too.)
