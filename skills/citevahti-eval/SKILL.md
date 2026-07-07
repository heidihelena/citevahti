---
name: citevahti-eval
description: Use when measuring or publishing CiteVahti's own accuracy — running the automatic claim-lexicon evaluation, checking it against its regression baseline, reasoning about how AI second-rater models are rated, or answering "how accurate is CiteVahti?". Follows ADR-0009's three evaluation objects (automatic lexicon eval, continuous model rating, pooled Atlas). Maintainer-facing; not for checking a researcher's manuscript (that is citevahti-dev).
---

# CiteVahti eval — measuring the tool honestly (ADR-0009)

CiteVahti's pitch is *"evidence tools held to evidence standards."* This skill is where
that stops being copy. It is **not** a single human-gold release gate — that framing was
wrong. Per [ADR-0009](../../docs/adr/0009-evaluation-and-model-quality.md), citation
checking is a **defence-in-depth stack** (human + lexical detector + AI models), and
evaluation has **three separate objects**, each measured differently.

The governing idea is the **cheese-hole principle**: safety comes from layers whose holes
don't line up. So a model that merely *agrees* with the human adds no defence — the best
layer catches what the others miss. Measurement is built around that, not around
conformity.

## Triggers

**Use when the maintainer asks to:** run or extend the automatic claim-lexicon eval; check
it against baseline; re-freeze the baseline after an intended change; reason about or
publish model ratings; prepare an eval-results page.

**Do NOT use for:** checking a researcher's manuscript (`citevahti-dev`), sweeping a
reference list (`citevahti-screen`), choosing/operating models (`citevahti-models`), or
the offline pytest suite (that's `secure-release`'s build gate).

## The three evaluation objects (keep them separate)

### 1. Claim-lexicon eval — automatic, you run it

The primary, always-on evaluation of the **deterministic lexical floor** (`text.py`). No
human-rater dependency — that is what makes it automatic.

```bash
python validation/claimcheck/eval_lexicon.py                  # score + per-phenomenon report
python validation/claimcheck/eval_lexicon.py --check          # CI gate: exit 1 on regression
python validation/claimcheck/eval_lexicon.py --write-baseline # re-freeze after an intended change
```

- Ground truth is the author-labelled `expected` relation in `lexicon_cases.jsonl`.
- The lexical layer is **one transparent slice with known holes** (paraphrase/synonymy;
  antonym contradictions with no negation cue). The eval **names the holes** per
  phenomenon — it does not pretend they're gone; the AI-model and human layers cover them.
- Regression policy: [`validation/claimcheck/acceptance-thresholds.md`](../../validation/claimcheck/acceptance-thresholds.md).
  **Precision is floored** (a flag must be worth interrupting for); **recall is published,
  not chased** — the inverted-U: over-flagging is worse than under-flagging, and widening a
  lexicon to chase recall is the wrong layer's job. A negated contradiction served as
  support must stay **0** (`tests/test_claimcheck_polarity.py`, `tests/test_lexicon_eval.py`).
- Regression here **blocks a release**; the known-hole categories are reported, not gated.

The two-blinded-human ledger (`validation/claimcheck/README.md`, `build_ledger.py` →
`fill_ledger.py` → `score_ledger.py`, Cohen's κ) is **retained as optional higher-assurance
calibration** of the lexical layer — never the release gate, and never a human bottleneck
on shipping.

### 2. Model rating — complementary catches, not agreement

Each **non-anonymous** AI second-rater model accrues a rating from **live** use, not from a
static set. The signal is the **validated complementary catch**: the model's blinded rating
**diverges** from the human, and the human **adopts** it — correcting the *statement* or the
*judgement* (better science). That is a hole covered. Agreement is cheap and scores little;
a model that never usefully diverges is a redundant layer. A low-value model → **suggest a
better-covering one** — the read-only `model_advisor` tool executes this from the project's
own records. `agreement_report` (METHODS.md) carries the model-provenance and human↔AI
comparison this builds on. Anonymous models are not rated — no identity, no track
record. This object is **not a release gate**; it drives model suggestion. Operated via
`citevahti-models`.

### 3. Atlas — pooled scoreboard + divergence maps (later)

The pooled corpus aggregates object 2 across contributors into a **model scoreboard** and
**divergence maps** (a layer over the Atlas evidence map). This is where higher-tier
confidence lives (ADR-0008: ≥5 → review, ~8+ → guideline). Emergent, real-world, later —
designed in ADR-0009, built when Atlas is ready.

## Publishing the numbers

Publish what you actually have, labelled by layer:

- The **lexicon-eval** numbers are real and publishable **now** — precision/recall per
  detector, the per-phenomenon breakdown **including the named holes**, N, and the date +
  version. A results page that hid the holes would misrepresent a one-slice floor as a
  complete detector — exactly the certification theater the brand forbids.
- **Model ratings** publish once there is live data; until then, say so.
- Present every number **as its layer's** number. A lexicon-eval figure is Layer-1 detector
  quality, never whole-system or guideline-grade accuracy.

`docs/KNOWN_LIMITATIONS.md` remains the honest baseline: no whole-system accuracy benchmark
yet. Copy that promises numbers must be commitment, not fact (`citevahti-claims` enforces).

## Hard rules

- **NEVER score a model on agreement with the human** — score complementary catches
  (ADR-0009). Rewarding agreement selects for redundant layers.
- **NEVER present the lexical-layer number as the whole system's accuracy**, and never hide
  the named holes — the holes are the honest part.
- **NEVER quote a number from `ledger.demo.jsonl`** (ILLUSTRATIVE) or from an unadjudicated
  human ledger.
- **NEVER let the lexicon eval regress silently** — `--check` and `test_lexicon_eval.py`
  block a support/contradiction precision or recall drop, and any negated-contradiction
  leak; re-freeze the baseline only for an *intended* change, with the change logged.
- **NEVER present single-assessor eval numbers as review- or guideline-grade evidence.**
  Layer 2 needs a panel; Layer 3 needs AtlasVahti pooling and more than five independent
  contributors — a better single detector cannot climb the ladder (ADR-0008).
- **NEVER treat agreement as accuracy** — descriptive agreement metrics are not ground
  truth (`docs/METHODS.md` transparency wording is the ceiling).
