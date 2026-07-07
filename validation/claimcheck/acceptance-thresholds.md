# claim-lexicon eval — regression policy

The regression thresholds for the **automatic** claim-lexicon evaluation
(`eval_lexicon.py`). This is **not** a human-gold release gate — that framing was wrong
(see [ADR-0009](../../docs/adr/0009-evaluation-and-model-quality.md), which supersedes the
earlier "no threshold pass, no release" version of this file). The lexical detector is one
transparent slice of a defence-in-depth stack; this file says only what counts as *making
that slice worse*.

- **Run it:** `python validation/claimcheck/eval_lexicon.py`
- **Gate it (CI):** `python validation/claimcheck/eval_lexicon.py --check`
  (also `tests/test_lexicon_eval.py`)
- **Re-freeze after an intended change:** `python validation/claimcheck/eval_lexicon.py --write-baseline`
- **Ground truth:** the author-labelled `expected` relation in `lexicon_cases.jsonl`
  (supports / contradicts / neither) — author gold, which is what makes the eval automatic.

## The principle: precision is a floor, sensitivity is a dial

There is no single correct sensitivity — the right amount of flagging is per-user and
per-context, an **inverted-U**: too few flags miss errors, but **too many is worse**
(over-flagging breaks the reviewer's flow and trains them to ignore the tool). So the
policy floors **precision** — a raised flag must be trustworthy enough to interrupt for —
and **publishes recall** as an operating point rather than chasing it. Chasing recall *in
the lexical layer* is the wrong layer's job: paraphrase and antonym holes are covered by
the AI-model and human layers (ADR-0009), not by widening a lexicon.

## What is gated (regression = release-blocking)

| Check | Rule | Why |
|---|---|---|
| Negated contradiction served as SUPPORT | **exactly 0** | The polarity guard's core invariant — an explicitly negated finding returned as support is false reassurance. Also `tests/test_claimcheck_polarity.py`. |
| Support-detector **precision** | **must not fall** below the committed baseline | A flag you can't trust is worse than no flag (the inverted-U). |
| Contradiction-detector **precision** | **must not fall** below baseline | Same. |
| Support / contradiction **recall** | **must not fall** below baseline | Recall is *published*, but a *drop* is still a regression — you don't get quietly worse. New capability that lifts recall re-freezes the baseline upward. |
| Population-mismatch flag **precision & recall** | **must not fall** below baseline | The advisory PICO flag (ADR-0009 "floor flags, AI confirms"): a supporting citation about a *different population*. Over-firing (false flags) is the worse side of the inverted-U, so precision matters most; recall is guarded too. |
| Certainty/overclaim flag **precision & recall** | **must not fall** below baseline | The advisory overclaim flag: the claim asserts plainly but the source hedges (correlational / weak effect). The **lowest-precision** flag (0.833) — its one known false-positive mode is a hedge word attached to a *covariate* rather than the relation ("…a benefit associated with adherence"), which is lexically indistinguishable from a real overclaim. Advisory only; the AI/human layer adjudicates. |

The baseline lives in `lexicon_baseline.json` (committed) and is compared by `--check`.
`test_lexicon_eval.py` also asserts the baseline's `n` matches the case set, so the guard
can't silently check against a stale number.

## What is reported but NOT gated (the named holes)

The lexical layer is **expected** to miss these — they are covered by the other cheese
slices, not by this one, so they are surfaced per-phenomenon and never gated:

- **`paraphrase_support`** — the *long tail* of synonymy the curated map doesn't cover.
  Common biomedical equivalents (heart attack ≈ myocardial infarction, hypertension ≈ high
  blood pressure) are now folded by the synonym map, but open paraphrase (e.g. meditation ≈
  mindfulness) still drops below threshold — by design, the AI-model layer's job.
- **`semantic_contradiction`** — a contradiction sharing no relation tokens at all.

`antonym_contradiction` **used to be listed here** and is **no longer a hole**: the
direction-aware polarity guard (`text.py`, two direction axes XOR-combined with negation)
now catches opposite-direction contradictions with no negation cue ("increased" vs
"reduced"). See the change log; it is now a *caught* category in the per-phenomenon report.

Naming holes is the point (ADR-0009): a results view that hid them would misrepresent a
one-slice floor as a complete detector.

## Current baseline (frozen 2026-07-07, n = 57)

| Detector | Precision | Recall |
|---|---|---|
| Support | 1.000 | 0.943 |
| Contradiction | 1.000 | 0.889 |
| Population-mismatch flag | 1.000 | 1.000 |
| Certainty/overclaim flag | 0.833 | 1.000 |

Negated-contradiction leaks: **0**. The support/contradiction detectors hold **1.000
precision** (neither cries wolf); support recall reached 0.943 after the inflectional
**stemmer** folded morphology and a small curated **synonym map** resolved common
biomedical equivalents (heart attack ≈ myocardial infarction, hypertension ≈ high blood
pressure). The **population-mismatch flag** scores 1.000/1.000 — the
important number being 0 false flags on its controls. The **certainty/overclaim flag** is
the one below 1.000 precision (0.833): recall is perfect, but one deliberately-included
hard control (a hedge word attached to a covariate, not the relation) is a false positive
the lexicon can't tell apart from a real overclaim — named, not hidden. The remaining
support-recall gap is genuine **synonymy/paraphrase**, the AI-model layer's job. These are
publishable *as the lexical-layer numbers*, not the whole system's accuracy.

## Not in scope here

**Model rating** (which AI second-rater to trust) and the **Atlas scoreboard / divergence
maps** are separate evaluation objects — continuous and pooled, respectively — and are
scored on *complementary catches*, not agreement. See ADR-0009 §3b–3c. Do not fold them
into this lexical regression policy.

## Change log (append-only)

| Date | Change | Reason |
|---|---|---|
| 2026-07-07 | Initial proposed v0 — human-gold κ release gate | first pre-registration scaffold |
| 2026-07-07 | v0.1 — precision sole gate, recall published (inverted-U) | maintainer steer: no universal sensitivity |
| 2026-07-07 | **v1 — repurposed to the `eval_lexicon.py` regression policy; the human-gold *release gate* is retired (ADR-0009). Baseline frozen (n=30).** | primary eval is the automatic lexicon run, not a human ledger; model rating & Atlas are separate objects |
| 2026-07-07 | **v2 — direction-aware polarity guard fixes the antonym hole the eval found. Support precision 0.714 → 1.000, contradiction recall 0.500 → 0.889. Baseline re-frozen (n=37, +7 held-out antonym/guard cases); `antonym_contradiction` moved from hole to caught category.** | close what the eval found; held-out pairs confirm it generalizes, not fits-to-test |
| 2026-07-07 | **v3 — conservative inflectional stemmer in the coverage-matching path. Support recall 0.688 → 0.812, precision held at 1.000; baseline re-frozen (n=37).** | close the inflection/morphology recall misses the eval flagged; measured precision-safe |
| 2026-07-07 | **v4 — population/PICO mismatch flag (age/sex/species) added to the floor as an advisory warning (ADR-0009 "floor flags, AI confirms"); scored by a new population detector (P 1.000 / R 1.000 over 10 cases, 0 false flags on controls). Baseline re-frozen (n=47).** | item 2/5 — catch the highest-value error class (right relation, wrong population); measured, conservative (silent on implicit populations) |
| 2026-07-07 | **v5 — certainty/overclaim flag (claim asserts plainly, source hedges: correlational / weak-effect) added as an advisory warning; new certainty detector P 0.833 / R 1.000 over 8 cases (one known covariate-association FP, kept as a hard control). High-precision cue set (no bare modals on the passage side). Baseline re-frozen (n=55).** | item 5/5 — catch overclaim (the "overstated" support value); measured, precision-first, FP mode named not hidden |
| 2026-07-07 | **v6 — small curated biomedical **synonym map** (heart attack ≈ myocardial infarction, hypertension ≈ high blood pressure, type-2 diabetes ≈ T2DM, …) folded in the coverage-matching path. Support recall 0.882 → 0.943, precision held at 1.000; baseline re-frozen (n=57).** | better-science: stop a student dropping a good citation because the source used a synonym; high-precision (unambiguous pairs only), long-tail paraphrase stays the AI layer's job |
