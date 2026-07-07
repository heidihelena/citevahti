---
name: citevahti-eval
description: Use when measuring or publishing CiteVahti's own accuracy — running the claim-check evaluation, filling or scoring the ground-truth ledger, checking precision/recall against the pre-registered acceptance thresholds, deciding whether a release may ship, or answering "how accurate is CiteVahti?". This is the production gate — no threshold pass, no release. Maintainer-facing; not for checking a researcher's manuscript (that is citevahti-dev).
---

# CiteVahti eval — the production gate

CiteVahti's pitch is *"evidence tools held to evidence standards"*. This skill is where
that stops being copy: a pre-registered ground-truth set, precision/recall on every
release, and a hard rule — **no threshold pass, no release**. The published numbers are
also the marketing asset; they exist to be shown, including when they're unflattering.

The measurement machinery already ships in `validation/claimcheck/` — read its
`README.md` before touching anything. This skill is the discipline around it.

## Triggers

**Use when the maintainer asks to:**
- run / fill / score the claim-check evaluation ledger
- check whether a release passes the accuracy gate
- extend the ground-truth set with new cases
- prepare or update the published eval-results page
- decide whether the production push continues (kill criterion)

**Do NOT use for:** checking a researcher's manuscript claims (`citevahti-dev`),
sweeping a reference list (`citevahti-screen`), or the offline pytest suite
(that's the build gate in `secure-release`, not the accuracy gate).

## The ground-truth set

The unit of analysis is a **(claim, passage) pair** — exactly what claim-check decides —
hand-curated, never auto-mined. The set must cover all four failure classes from the
product frame:

| Class | What it tests |
|---|---|
| **correct** | citation genuinely supports the claim (true-negative floor for the mismatch detector) |
| **mismatched** | source exists but does not support the claim (quotation error) |
| **retracted** | source is retracted / has an expression of concern |
| **fabricated** | reference does not exist (no resolvable DOI/PMID) |

Retracted and fabricated cases key on **DOI/PMID** — that's the shipped detection
mechanism (`docs/KNOWN_LIMITATIONS.md`); items with neither identifier are untestable by
design and belong in the set only as documented exclusions.

## The protocol (pre-registered — do not improvise)

Mirrors `validation/claimcheck/README.md` exactly:

```bash
python validation/claimcheck/build_ledger.py            # seed from the curated set
python validation/claimcheck/fill_ledger.py rater1      # BLINDED human pass 1
python validation/claimcheck/fill_ledger.py rater2      # BLINDED human pass 2
python validation/claimcheck/fill_ledger.py adjudicate  # reveal + adjudicate
python validation/claimcheck/score_ledger.py validation/claimcheck/ledger.jsonl
```

Non-negotiables, in order:

1. **κ first.** Cohen's κ between the two blinded raters is reported before any
   detector metric. **κ < 0.6 voids the ground truth** — sharpen the rubric and re-rate;
   the precision/recall numbers do not exist until κ passes.
2. **Measure before tuning.** No threshold, stopword, or lexicon change without a
   scored baseline to compare against. Tuning against an unfilled ledger is guessing.
3. **The LLM advisor is scored against the same human gold**, never against claim-check
   itself, and the **correlated-error count is reported** so agreement is never mistaken
   for accuracy.
4. **`score_ledger.py` refuses to invent labels** — keep it that way. Missing labels are
   reported as missing, not imputed.
5. **`ledger.demo.jsonl` is ILLUSTRATIVE.** Cite no number from it, ever.

## Acceptance thresholds — the gate

Thresholds are **pre-registered**: written down (in `validation/claimcheck/`, committed)
*before* the scoring run they gate, and changed only between cycles with the change
logged and reasoned. Deciding the floor after seeing the numbers is the exact failure
this skill exists to prevent.

At release time (`citevahti-release` calls this as its first gate):

- **PASS** — every pre-registered floor met → release proceeds; numbers go to the
  eval-results page with the release.
- **FAIL** — any floor missed → **no release.** File the gap, run an improvement cycle,
  re-measure on the *same protocol*.

**Kill criterion (from the production plan, `docs/BETA_TO_PRODUCTION.md`):** if
mismatch-detection precision stays below the pre-registered floor after **two
improvement cycles**, the production push stops — CiteVahti reverts to
"internal tool" status and the public positioning changes accordingly. This is a
pre-commitment; do not renegotiate it mid-cycle.

## Publishing the numbers

Every scored run that gates a release gets published — precision, recall, F1 per
detector, κ, N, the four class counts, the correlated-error count, and the date +
version measured. Include what *failed* or was excluded; a results page with only
flattering rows is exactly the certification theater the brand forbids.

Until the first filled ledger is scored, the honest public statement is the one in
`docs/KNOWN_LIMITATIONS.md`: **no published accuracy benchmark yet** — and any copy
promising published numbers must be phrased as commitment, not fact
(`citevahti-claims` enforces this).

## Hard rules

- **NEVER quote a number from the demo ledger** or from an unadjudicated ledger.
- **NEVER report precision/recall without κ** alongside it.
- **NEVER move a threshold after seeing the run it gates.**
- **NEVER let a release ship on a failed or missing gate** — "we'll measure next
  release" is the failure mode, not a mitigation.
- **NEVER present descriptive agreement metrics as validation** of the AI or as ground
  truth (`docs/METHODS.md` transparency section wording is the ceiling).
