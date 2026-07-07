# Beta → production: required skills

*The plan of record for the production push. The skills it specifies now exist under
`skills/` — this doc keeps the frame, the build order, and the kill criterion in one place.*

Product-task frame (per Vahtian tool rules):

- **User:** researcher/reviewer accountable for citation accuracy.
- **Problem:** unverified claim–citation pairs; retractions; hallucinated references.
- **Input:** manuscript + Zotero library. **Output:** tiered, reasoned citation report.
- **Uncertainty reduced:** which citations are unsupported/retracted/nonexistent.
- **Uncertainty remaining:** semantic mismatch detection is imperfect; recall < 100% and
  must be published, not hidden.
- **Data sensitivity:** low (local-first; no health data). **Claims that must not be
  made:** "guarantees accuracy", "AI-verified", "catches all errors", any certification
  language.

## The skill roster (each a SKILL.md alongside citevahti-dev)

| # | Skill | Role | CFO class | Status |
|---|---|---|---|---|
| 1 | [`citevahti-eval`](../skills/citevahti-eval/SKILL.md) | **Honest self-measurement** ([ADR-0009](adr/0009-evaluation-and-model-quality.md)): three eval objects — an automatic claim-lexicon eval we run, continuous model rating by *complementary catches* (not agreement), and a pooled Atlas scoreboard later. Not a human-gated release gate. | product-building + reputational | **Built + running + already drove a fix.** `eval_lexicon.py` produces real lexical-layer numbers (support P 1.00 / R 0.69, contradiction P 1.00 / R 0.89, 0 negation leaks), CI-guarded by `test_lexicon_eval.py`. It found a support-precision hole (antonym contradictions), which the direction-aware polarity guard then closed (0.714 → 1.000), then drove stemming (recall 0.69 → 0.81) and a population/PICO flag. **Model rating**: the per-model complementary-catch scoreboard now computes locally from the ledger (`agreement_report`, read-only); the **pooled Atlas** scoreboard remains roadmap. Human ledger retained as optional calibration. |
| 2 | [`citevahti-release`](../skills/citevahti-release/SKILL.md) | Parity and shipping: MCP server / desktop extension / panel / VS Code feature parity, version lockstep, changelog, Zenodo DOI per release, rollback notes. Orchestrates the existing `secure-release` gates. | product-building | **Built.** |
| 3 | [`citevahti-claims`](../skills/citevahti-claims/SKILL.md) | Audits every public artifact (site copy, README, LinkedIn, docs) against the must-not-claim list and evidence-tier language before publication. Cheap to build, protects the brand core. | reputational / sales-enabling | **Built.** |
| 4 | [`citevahti-support`](../skills/citevahti-support/SKILL.md) | Triage template, known-issues register, response snippets, escalation criteria (data-loss or false-verified reports = immediate). | administrative, mandatory for paid users | **Built** — activate before first paying customer. |
| 5 | [`citevahti-onboarding`](../skills/citevahti-onboarding/SKILL.md) | Docs/quickstart generation per distribution channel (MCP config, extension install, web/panel). | enabling | **Built** — hold doc regeneration until eval + release outputs stabilize; docs churn until then is wasted. |
| 6 | [`citevahti-models`](../skills/citevahti-models/SKILL.md) | Choose/compare the AI second-rater model; run a topic through several models; the 3-model guideline pre-check. Rated by complementary catches, not agreement ([ADR-0009](adr/0009-evaluation-and-model-quality.md)). | product-building | **Built** (workflow); scoreboard + divergence maps are Atlas roadmap. |

## Kill criterion for the production push

If the automatic **claim-lexicon eval regresses** (support/contradiction precision falls
below the frozen baseline, or a negated contradiction is served as support) and it cannot
be recovered after **two improvement cycles**, stop and treat the lexical layer as
not-ship-ready. Note the distinction from ADR-0009: this gate is about the *lexical slice's*
precision, not a whole-system accuracy number (which comes later, from model rating +
Atlas). The public positioning must not outrun what the current layer's numbers support.

## Related

- Launch copy draft: [`docs/marketing/launch-copy-v1.md`](marketing/launch-copy-v1.md)
  (carries repo-verification notes that must be resolved before publication)
- The release discipline itself: `.claude/skills/secure-release/` + [`RELEASING.md`](RELEASING.md)
- What may never be claimed: [`DISCLOSURE.md`](DISCLOSURE.md) ·
  [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) · [`METHODS.md`](METHODS.md)
