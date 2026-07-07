# claim-check acceptance thresholds — the pre-registered release gate

This file is the **pre-registration** the `citevahti-eval` skill enforces: the accuracy
floors a release must clear, **written down before the scoring run that gates it**.
Deciding a floor after seeing the numbers is the exact failure the gate exists to
prevent — so the rule is simple: **change these values only *between* cycles, never after
a run you are about to gate on, and log every change below.**

- **Pre-registration status:** *proposed v0 — awaiting maintainer confirmation before the
  first scored run.* No ledger has been filled or scored yet (see
  `../../docs/KNOWN_LIMITATIONS.md`: "No published accuracy benchmark yet"), so these
  values may still be revised — that revision is still *before results* and therefore
  still a valid pre-registration. Once the first `score_ledger.py` run is used to gate a
  release, these numbers **freeze** and only move by a logged between-cycle change.
- **Scored by:** `python validation/claimcheck/score_ledger.py validation/claimcheck/ledger.jsonl`
- **Unit of analysis:** a human-adjudicated `(claim, passage)` relation
  ∈ {supports, contradicts, neither}, per `README.md`.

## Gate 0 — ground-truth validity (must pass, or there are no metrics)

| Check | Floor | Why |
|---|---|---|
| Inter-rater Cohen's κ (rater1 vs rater2) | **≥ 0.60** | Below substantial agreement there is no usable ground truth; the detector metrics are void until the rubric is sharpened and the raters re-rate. Already surfaced by `score_ledger.py` as `WEAK`/`OK`. |
| Adjudicated pairs, N | **≥ 50** total | Small N makes a precision point estimate meaningless. |
| Per-class coverage | **≥ 10** genuinely-supports **and** **≥ 10** genuinely-contradicts pairs | A precision floor on a class with 3 examples is noise. |

If Gate 0 fails, the run does not produce a release verdict — it produces a
"fill/repair the ledger" instruction.

## Gate 1 — detector floors (the release gate)

Scored against the adjudicated gold. Precision is gated (a false call is the harmful
direction — see rationale); recall is **published, not hidden**, with a target that drives
improvement cycles rather than hard-blocking the first release.

| Metric | Floor | Gate? | Rationale |
|---|---|---|---|
| Contradictions leaking into SUPPORT | **exactly 0** | **hard** | A contradicting source returned as support is false reassurance — the worst failure. This is the shipped polarity-guard invariant (`tests/test_claimcheck_polarity.py`); the ledger must confirm it holds on real gold, not just unit fixtures. |
| **Mismatch (contradiction) detector — precision** | **≥ 0.80** | **hard — this is the kill-criterion metric** | When CiteVahti flags a claim–source mismatch, it should usually be right; false alarms train users to ignore flags. `docs/BETA_TO_PRODUCTION.md`'s kill criterion is defined on *this* number. |
| Support detector — precision | **≥ 0.85** | **hard** | A pair shown as a support-candidate that does not actually support is the reassurance failure a citation tool exists to prevent; held slightly higher than mismatch precision. |
| Mismatch detector — recall | ≥ 0.60 (**target**, published) | soft | The lexical floor is deliberately conservative; missed mismatches are the honest weak point. Report the number every release; a miss opens an improvement cycle, it does not alone block release 1. |
| Support detector — recall | ≥ 0.60 (**target**, published) | soft | Same posture; reported, not hidden. |

## Gate 2 — the AI advisor is measured, never trusted into the gate

The optional LLM advisor is scored against the **same human gold**, never against
claim-check, and the **correlated-error count** (`score_ledger.py`) is reported so
agreement between claim-check and the LLM is never mistaken for accuracy. The advisor's
numbers are **published but do not gate a release** — the blinded second-rater role is
advisory by design (ADR-0001), and letting it into the gate would launder AI agreement
into an accuracy claim.

## Scope note — what this ledger does and does not gate

This ledger gates the **semantic support/mismatch detector**. **Retraction and
fabricated-reference detection are deterministic DOI/PMID mechanisms**, not lexical
classifiers — they are gated by functional tests (does the retraction/dedupe check fire
and fail-closed), not by precision/recall here. Items with neither a DOI nor a PMID are
untestable by design (`docs/KNOWN_LIMITATIONS.md`) and belong in the set only as
documented exclusions, never as silent misses.

## The verdict rule

- **PASS** — Gate 0 passes **and** every *hard* floor in Gate 1 is met → release may
  proceed (`citevahti-release` gate 0). Publish all numbers, including the soft-target
  recalls and the advisor figures, with N, κ, class counts, date, and version.
- **FAIL** — any hard floor missed → **no release.** File the gap, run an improvement
  cycle, re-measure on this same protocol.
- **Kill criterion** (`docs/BETA_TO_PRODUCTION.md`) — if mismatch-detector precision stays
  below its floor after **two** improvement cycles, the production push stops; CiteVahti
  reverts to internal-tool positioning. Pre-committed; not renegotiable mid-cycle.

## Change log (append-only — every threshold change, with reason and date)

| Date | Change | Reason | Made before or after a gated run? |
|---|---|---|---|
| 2026-07-07 | Initial proposed v0 (floors above) | First pre-registration; scaffolds the gate ahead of the first filled ledger | Before — no run has been scored |
