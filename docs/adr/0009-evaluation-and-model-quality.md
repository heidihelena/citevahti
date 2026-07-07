# ADR-0009 — Evaluation & model-quality architecture (defence in depth)

- **Status:** Accepted (2026-07-07)
- **Date:** 2026-07-07
- **Builds on:** [ADR-0001](0001-citation-integrity-architecture.md) (human rates first,
  AI is a blinded second rater, human decides), [ADR-0007](0007-local-web-app-and-http-surface.md)
  (the panel prepares prompts; the assistant runs the model), and
  [ADR-0008](0008-evidence-confidence-tiers.md) (confidence scales with the count of
  *independent assessors* of a claim).
- **Scope note.** This record fixes the *evaluation architecture* — how we know the tool
  works, and which AI model to trust. The commercial shape of any hosted scoreboard or
  guideline offering stays **private**, per ADR-0003.

## 1. Context

Two questions a single per-claim judgment cannot answer on its own:

> How do we **know** claim-check is any good — and **which AI model** should sit in the
> blinded second-rater seat?

An earlier attempt answered both with one instrument: a two-blinded-human ledger with a
Cohen's κ floor, turned into a hard "no threshold pass, no release" gate, and a model
score defined as **agreement with the human**. Both were wrong, for the same reason.

## 2. The governing idea — defence in depth (the "cheese-hole" principle)

Citation checking is a **Swiss-cheese stack**: the human, the lexical detector, and one or
more AI models are independent layers, each with holes (misses). A citation error reaches
print only if it passes through **every** layer's holes at once. Safety therefore comes
from layers whose holes **do not line up**.

The decisive consequence: **a model that mostly *agrees* with the human adds no defence —
its holes line up with the human's.** The best model is the one that **catches what the
human misses**. So model quality is measured by **validated complementary catches**, not
by agreement. Divergence is the *product*, not noise to suppress.

## 3. Decision — three evaluation objects, kept separate

| Object | Who runs it | What it measures | Gate? |
|---|---|---|---|
| **1. Claim-lexicon eval** | **The AI, automatically** (on demand + CI) | the deterministic lexical floor (`text.py`) against author-labelled cases | precision + no-regression; recall **published**, not gated |
| **2. Model rating** | continuous, from **live human adjudication** | each identifiable model's **complementary catches** — divergences the human adopts | not a gate; drives "suggest a better-covering model" |
| **3. Atlas** | the **pooled corpus** (later) | scoreboard + divergence maps + ADR-0008 assessor tiers | not a gate; emergent, real-world |

### 3a. Claim-lexicon eval — automatic, run by us

The lexical detector is **one transparent slice with known holes** (paraphrase/synonymy it
can't see; antonym contradictions carrying no negation cue). It is *not meant to be
complete*. `validation/claimcheck/eval_lexicon.py` runs the real `text.py` over curated,
author-labelled `(claim, passage, expected)` cases — **no human-rater dependency**, which
is what makes it automatic — and **names the holes** (per-phenomenon breakdown) instead of
hiding them. Regression policy lives in
[`validation/claimcheck/acceptance-thresholds.md`](../../validation/claimcheck/acceptance-thresholds.md):

- **precision** must not fall (a raised flag must be worth interrupting for);
- **recall** is *published*, not gated — the **inverted-U**: too few flags miss errors, but
  over-flagging is *worse* (it breaks the reviewer's flow and trains them to ignore the
  tool), so there is no universal sensitivity to clear, and chasing recall *in this layer*
  is the wrong layer's job;
- an explicitly-**negated contradiction served as support must stay 0** (the polarity
  guard, `tests/test_claimcheck_polarity.py` + `tests/test_lexicon_eval.py`).

The two-blinded-human ledger (`validation/claimcheck/README.md`) is **retained as optional
higher-assurance calibration**, never as the release gate.

### 3b. Model rating — complementary catches, not agreement

Each **non-anonymous** model (you can only build a track record for a model you can
identify) accrues a rating from live use: when its blinded rating **diverges** from the
human and the human then **adopts** the divergence — correcting the *statement* or the
*judgement* — that is a **validated catch** (better science, and the model covered a hole).
Agreement is cheap and scores little; a model that never usefully diverges is a redundant
layer. **A low-value model → suggest a better-covering one** (panel *Settings → AI second
opinion*). `agreement_report` (METHODS.md) already carries the model-provenance and
human↔AI comparison this builds on. Anonymous models are not rated (no stable identity).

The read-only **`model_advisor`** tool executes this rating: it ranks the identifiable
models by catch-rate over an evidence floor of resolved divergences, recommends the
best-evidenced one, stays silent on any model without enough resolved divergences to
judge, and — given a named model that rates low — suggests a better-evidenced alternative.
It scores complementary value, never agreement, and adjudicates nothing.

### 3c. Atlas — pooled scoreboard and divergence maps (later)

The pooled corpus aggregates 3b across contributors into a **model scoreboard** (which
models cover the most holes) and **divergence maps** — a layer over the shipped Atlas
evidence map showing where models diverge from each other and from human consensus, by
claim/topic. This is where higher-tier confidence lives (ADR-0008: ≥5 → review, ~8+ →
guideline). Emergent and real-world; it comes *later*, with usage.

## 4. The models layer (product surface)

A `citevahti-models` skill operates this dimension: choose a second-rater model by its
scoreboard rating, **run a topic across several models**, read the divergence, act on a low
rating. The motivating workflow: **a serious guideline group runs the same topic through 3
independent models before starting**, and the divergence map shows where the AI assessments
disagree, so scarce human effort goes where it is contested.

## 5. Invariants (unchanged, and load-bearing here)

- **The human decides.** AI — one model or several — **never issues a verdict** (ADR-0001).
- **Multi-model agreement is a *screening* signal, not an evidence tier.** 3 models running
  a topic is Layer-0 screening — *leads, not verdicts* (ADR-0008 §Layer 0). It **prepares**
  guideline work; it does not confer guideline grade, which still needs the human
  independent-assessor count.
- **Only identifiable models are rated.** No reputation without identity.
- **Eval numbers are per-layer.** A lexicon-eval number is Layer-1 detector quality; it is
  never presented as review- or guideline-grade validation.

## 6. Consequences

- "Evaluation" stops being a human-gated release bottleneck and becomes: an **automatic**
  lexicon eval we run now (with real, publishable numbers), a **continuous** model rating
  from live use, and a **pooled** Atlas layer later.
- Model selection optimises for **coverage**, not conformity — the honest and safer target.
- `acceptance-thresholds.md` is repurposed from "release gate" to **lexicon-eval regression
  policy**; `citevahti-eval` and a new `citevahti-models` skill point here.
- New surfaces committed to the roadmap: the Atlas **scoreboard** + **divergence maps**, and
  the multi-model topic run. Built when Atlas is ready; designed here.
