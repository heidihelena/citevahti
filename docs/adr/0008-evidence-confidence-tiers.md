# ADR-0008 — Evidence confidence tiers (the contributor-count ladder)

- **Status:** Accepted (2026-06-18)
- **Date:** 2026-06-18
- **Builds on:** [ADR-0001](0001-citation-integrity-architecture.md) (the claim-support
  ledger is the spine; one assessor per judgment), [ADR-0003](0003-hosted-layer-and-open-core.md)
  (open-core boundary; the ≥5 aggregate-data floor), and
  [ADR-0007](0007-local-web-app-and-http-surface.md) (the panel never calls an AI itself —
  it prepares prompts; the assistant runs the model).
- **Scope note.** This record fixes the *epistemic architecture* — how confidence in a claim
  scales with the number of independent assessors, and how AI assists at each tier. The
  commercial shape of any hosted review/guideline offering stays **private**, per ADR-0003;
  the public record is the architecture, not the business model.

## 1. Context

CiteVahti produces a per-claim **support judgment** from *one* assessor: the human rates
first, the AI is a blinded second rater, nothing is decided autonomously (ADR-0001). The
open question this ADR settles is the one a single judgment cannot answer on its own:

> When does an individual claim judgment become **review-grade** or **guideline-grade**
> evidence?

The answer is the same mechanism evidence hierarchies already use — **more *independent*
assessors of the same claim raises confidence.** We fix this ladder now, before the
collaborative tiers are built, so the data model, the join key, and the consent rules are
designed for it rather than retrofitted.

Two existing facts constrain the design:

- the **≥ 5 distinct-contributor floor** for any aggregate view (ADR-0003 and the
  [contributor privacy notice](../CONTRIBUTOR_PRIVACY.md));
- the **`claim_text_hash`** join key (the shared, normalized claim fingerprint) and the
  existing `claim-support` rating spine — both already shipped.

## 2. Decision — the ladder

Confidence in a claim scales with the count of **independent assessors of the same claim**
(joined on `claim_text_hash`). Four layers:

| Layer | Independent assessors | Epistemic status | AI's role |
|---|---|---|---|
| **0 — Screening** | – (pre-assessment) | a topic → candidate claims + evidence | AI screens a topic into candidate claims and suggests **nearby** articles (proximity in the claim↔evidence map). Leads, not verdicts. |
| **1 — Individual** | 1 | single-assessor judgment | blinded second opinion; never decides |
| **2 — Review** | 2–7 (panel) · 5–7 (pool) | review-level | aggregate agreement / "X of N support" |
| **3 — Guideline** | ~8 + | guideline-level | consensus surface ("X of 10 support") |

The intuition it mirrors is deliberate: a single expert opinion → a systematic-review panel
→ a guideline working group. The corpus's concrete output becomes, e.g., *"supported at
review-level — 6 independent assessors agree"* rather than an undifferentiated verdict.

## 3. Two mechanisms, one ladder

The ladder is realized **two ways**, which must not be conflated:

**(a) Organized panel** — named, consented assessors rate the *same* claims inside one
project; the output is **"X of N support"**. This is the house's review tier (2–7 raters)
and guideline tier (a working group of ~10). It is **orchestration of CiteVahti's existing
`claim-support` tools** (`start_support_rating` → `submit_ai_support_rating` → decision →
`preview_write` / `commit_write` → `get_provenance`) plus a shared collection — **not new
core code.** Because the assessors are named and consented within the project, **no
k-anonymity floor is needed** here.

**(b) Pooled corpus** — de-identified contributions from *independent* researchers, joined on
`claim_text_hash`, surfacing emergent agreement (AtlasVahti). Here the **≥ 5 floor *is* the
Layer-1 → Layer-2 boundary**: below 5 distinct contributors a claim stays individual (no
cross-contributor view is shown); at ≥ 5 it becomes a visible pooled signal. The
k-anonymity floor and the epistemic floor **coincide** — one number, two meanings, not a
separate privacy kludge.

## 4. AI assistance per layer (including the new Layer 0)

- **Layer 0 — topic screening (new surface).** A **"Screen a topic"** button in the panel
  hands the assistant an `ai-screen` prompt for a topic; the AI proposes **candidate claims**
  to assess and **nearby/related articles** (corpus proximity once AtlasVahti exists;
  PubMed/related-article search otherwise). It emits *leads that feed the assess loop, never
  verdicts.* Per ADR-0007 the panel only *prepares* the prompt — the assistant runs the
  model — mirroring the existing `run_claim_tests` and Word→claims handoffs.
- **Layers 1–3.** The AI stays the **blinded second rater**. Aggregate tiers compute
  "X of N" / pooled agreement deterministically; AI never produces an autonomous tier verdict.

## 5. Implementation notes

- **Tier function:** `tier = f(distinct_independent_assessor_count(claim_text_hash))`. Panel
  mode counts named raters in the project; pool mode counts distinct contributor ids in the
  corpus behind the ≥ 5 gate.
- **Reuse the spine:** no new rating engine. The review/guideline tiers are orchestration +
  a collection over the shipped `claim-support` path; `agreement_status` and the
  `does_not_support` / `contradicts` labels are already first-class, so the tiers keep
  conflicts rather than collapsing them.
- **The one genuinely new build is Layer 0:** a topic-screening prompt + button (prompt
  preparation only — the panel never calls an AI itself, ADR-0007). Small, additive.

## 6. Consequences

- The corpus gains a concrete, honest output grade — review-level / guideline-level — tied to
  a *count of independent assessors*, not a single opinion dressed up as consensus.
- The ≥ 5 privacy floor and the individual → review epistemic boundary become the **same**
  line; the aggregate-data governance of ADR-0003 needs no special case.
- Review- and guideline-tier tools are positioned as **orchestrations of CiteVahti**, keeping
  the core small and the spine single-sourced.
- One new surface is committed to the roadmap: the **Layer-0 topic-screening** prompt + button.
- The commercial shape of any hosted tier remains private (ADR-0003); this ADR is architecture.
