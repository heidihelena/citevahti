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

The baseline lives in `lexicon_baseline.json` (committed) and is compared by `--check`.
`test_lexicon_eval.py` also asserts the baseline's `n` matches the case set, so the guard
can't silently check against a stale number.

## What is reported but NOT gated (the named holes)

The lexical layer is **expected** to miss these — they are covered by the other cheese
slices, not by this one, so they are surfaced per-phenomenon and never gated:

- **`paraphrase_support`** — synonymy/inflection drops token overlap below threshold
  (e.g. "heart attack" vs "myocardial infarction"). Reported recall loss, by design; the
  AI-model layer covers it.
- **`semantic_contradiction`** — a contradiction sharing no relation tokens at all.

`antonym_contradiction` **used to be listed here** and is **no longer a hole**: the
direction-aware polarity guard (`text.py`, two direction axes XOR-combined with negation)
now catches opposite-direction contradictions with no negation cue ("increased" vs
"reduced"). See the change log; it is now a *caught* category in the per-phenomenon report.

Naming holes is the point (ADR-0009): a results view that hid them would misrepresent a
one-slice floor as a complete detector.

## Current baseline (frozen 2026-07-07, n = 37)

| Detector | Precision | Recall |
|---|---|---|
| Support | 1.000 | 0.812 |
| Contradiction | 1.000 | 0.889 |

Negated-contradiction leaks: **0**. Both detectors hold **1.000 precision** (neither cries
wolf). Support recall rose from 0.688 to 0.812 once a conservative inflectional **stemmer**
folded morphology (antidepressants≈antidepressant, increases≈increased) in the matching
path — precision held, so no false matches. The remaining recall gap is genuine
**synonymy/paraphrase** ("heart attack" vs "myocardial infarction"), which is the
AI-model layer's job, not the lexicon's. These are publishable *as the lexical-layer numbers*, not as the
whole system's accuracy.

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
