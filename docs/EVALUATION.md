# CiteVahti — evaluation results

> _Generated from `validation/claimcheck/lexicon_baseline.json` by `validation/eval_report.py`. Do not edit by hand — re-run the generator._

CiteVahti holds itself to the evidence standards it promotes. Per [ADR-0009](adr/0009-evaluation-and-model-quality.md), evaluation has **three objects**, measured differently. This page reports each one honestly — including what is **not** yet measured.

## 1. Claim-lexicon eval (automatic, measured now)

The deterministic lexical detector, scored against a curated, author-labelled set of **57** `(claim, passage)` cases (`validation/claimcheck/lexicon_cases.jsonl`). Precision is floored in CI; recall is published, not chased (the inverted-U — over-flagging is worse than under-flagging). Advisory flags (population, certainty) are surfaced for the human/AI layer to adjudicate, never as verdicts.

| Detector | Precision | Recall |
|---|---|---|
| Support | 1.000 | 0.943 |
| Contradiction | 1.000 | 0.895 |
| Population-mismatch flag | 1.000 | 1.000 |
| Certainty/overclaim flag | 0.833 | 1.000 |

Negated-contradiction leaks (a negated finding served as support): **0** — a hard-zero invariant. The remaining recall gaps are genuine synonymy/paraphrase, which is the AI-model layer's job, not the lexicon's (the eval names those holes rather than hiding them). These are the **lexical-layer** numbers — not the whole system's accuracy.

## 2. Model rating (continuous, accrues from use)

Each identifiable AI second-rater model earns a **complementary-catch** score: a *validated divergence* — the model disagreed with the human and the human's adjudicated final matched the AI (the model was right where the human's first take was not). Agreement scores nothing (the cheese-hole principle: a model that only agrees adds no defence). This is computed **read-only** from a project's own rating ledger by `agreement_report`; there is no fixed number to publish — it is a per-project, per-model tally that grows with real use.

## 3. Pooled Atlas scoreboard + divergence maps (roadmap)

Across contributors, object 2 aggregates into a model scoreboard and divergence maps, and confidence tiers scale with the count of independent assessors ([ADR-0008](adr/0008-evidence-confidence-tiers.md): ≥5 → review, ~8+ → guideline). Emergent and real-world; built when AtlasVahti ships.

## What is NOT yet measured

- **No whole-system accuracy benchmark.** The numbers above are the *lexical layer's*. Human inter-rater reliability, human↔AI agreement, and end-to-end system accuracy have not been measured and published — see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). The pre-registered human ground-truth protocol exists (`validation/claimcheck/`) but its rater columns are unfilled; the model-rating data (object 2) accrues only as pilots use the tool.
- Treat CiteVahti as a disciplined **workflow**, not a validated **oracle**. Every number here is a *layer's* number, never a certification of a citation.

