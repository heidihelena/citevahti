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
| 1 | [`citevahti-eval`](../skills/citevahti-eval/SKILL.md) | **The production gate.** Ground-truth test set (correct, mismatched, retracted, fabricated citations); precision/recall on every release; pre-registered acceptance thresholds. No threshold pass, no release. Published eval numbers are the credibility moat. | product-building + reputational | **Built.** Ledger exists (`validation/claimcheck/`); human rating passes not yet run — no publishable numbers yet. |
| 2 | [`citevahti-release`](../skills/citevahti-release/SKILL.md) | Parity and shipping: MCP server / desktop extension / panel / VS Code feature parity, version lockstep, changelog, Zenodo DOI per release, rollback notes. Orchestrates the existing `secure-release` gates. | product-building | **Built.** |
| 3 | [`citevahti-claims`](../skills/citevahti-claims/SKILL.md) | Audits every public artifact (site copy, README, LinkedIn, docs) against the must-not-claim list and evidence-tier language before publication. Cheap to build, protects the brand core. | reputational / sales-enabling | **Built.** |
| 4 | [`citevahti-support`](../skills/citevahti-support/SKILL.md) | Triage template, known-issues register, response snippets, escalation criteria (data-loss or false-verified reports = immediate). | administrative, mandatory for paid users | **Built** — activate before first paying customer. |
| 5 | [`citevahti-onboarding`](../skills/citevahti-onboarding/SKILL.md) | Docs/quickstart generation per distribution channel (MCP config, extension install, web/panel). | enabling | **Built** — hold doc regeneration until eval + release outputs stabilize; docs churn until then is wasted. |

## Kill criterion for the production push

If `citevahti-eval` shows mismatch-detection precision below the pre-registered floor
after **two improvement cycles**, revert to **"Proceed only as internal tool"** and keep
it as CiteVahti-powered content instead.

## Related

- Launch copy draft: [`docs/marketing/launch-copy-v1.md`](marketing/launch-copy-v1.md)
  (carries repo-verification notes that must be resolved before publication)
- The release discipline itself: `.claude/skills/secure-release/` + [`RELEASING.md`](RELEASING.md)
- What may never be claimed: [`DISCLOSURE.md`](DISCLOSURE.md) ·
  [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) · [`METHODS.md`](METHODS.md)
