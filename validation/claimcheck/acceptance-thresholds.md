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

## The one principle: precision is a gate, sensitivity is a dial

There is no single correct sensitivity. Different reviewers, fields, and manuscripts want
different amounts of flagging, and the right amount is an **inverted-U**: too few flags
miss real errors, but **too many is worse** — over-flagging breaks the reviewer's flow and
trains them to ignore the tool (alert fatigue). "In-flow" is the target, not maximum
recall.

So this file gates exactly **one** thing: **precision** — that a flag, when raised, is
trustworthy enough to be worth interrupting for. It does **not** gate a sensitivity level.
Recall is **published as an operating-point curve** so each user can choose where they sit;
it is never maximized toward a number. Chasing recall past the flow point is a regression,
not a win.

## Gate 0 — ground-truth validity (must pass, or there are no metrics)

| Check | Floor | Why |
|---|---|---|
| Inter-rater Cohen's κ (rater1 vs rater2) | **≥ 0.60** | Below substantial agreement there is no usable ground truth; the detector metrics are void until the rubric is sharpened and the raters re-rate. Already surfaced by `score_ledger.py` as `WEAK`/`OK`. |
| Adjudicated pairs, N | **≥ 50** total | Small N makes a precision point estimate meaningless. |
| Per-class coverage | **≥ 10** genuinely-supports **and** **≥ 10** genuinely-contradicts pairs | A precision floor on a class with 3 examples is noise. |

If Gate 0 fails, the run does not produce a release verdict — it produces a
"fill/repair the ledger" instruction.

## Gate 1 — detector floors (the release gate)

Scored against the adjudicated gold. **Precision is the only gate** (a false flag is the
harmful direction — see the principle above). Recall is **published as an operating-point
curve, not gated**: it locates the user's sensitivity dial, it is never a bar to clear.

| Metric | Floor | Gate? | Rationale |
|---|---|---|---|
| Contradictions leaking into SUPPORT | **exactly 0** | **hard** | A contradicting source returned as support is false reassurance — the worst failure. This is the shipped polarity-guard invariant (`tests/test_claimcheck_polarity.py`); the ledger must confirm it holds on real gold, not just unit fixtures. |
| **Mismatch (contradiction) detector — precision** | **≥ 0.80** | **hard — this is the kill-criterion metric** | When CiteVahti flags a claim–source mismatch, it should usually be right; over-flagging trains users to ignore flags and is the worse side of the inverted-U. `docs/BETA_TO_PRODUCTION.md`'s kill criterion is defined on *this* number. |
| Support detector — precision | **≥ 0.85** | **hard** | A pair shown as a support-candidate that does not actually support is the reassurance failure a citation tool exists to prevent; held slightly higher than mismatch precision. |
| Mismatch detector — recall @ the gated precision | published, **not gated** | none | Report the recall reached *at* the precision floor, plus the full precision/recall curve. Missed mismatches are the honest weak point; improvement cycles target missed **high-value** mismatches — never by pushing false-alarm volume past the flow point. |
| Support detector — recall @ the gated precision | published, **not gated** | none | Same posture: reported as an operating point the user reads, not a bar the release clears. |

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

It also gates **single-assessor quality only** — ADR-0008 Layer 1 (individual). It
**cannot establish review-grade (Layer 2) or guideline-grade (Layer 3) confidence**: those
come from *more independent assessors of the same claim*, not from a better single
detector. Review-grade needs an organized panel (2–7 raters); **guideline-grade is not
reachable without AtlasVahti's pooled corpus and more than five independent contributors**
(~8+), per [ADR-0008](../../docs/adr/0008-evidence-confidence-tiers.md). A high precision
number here is Layer-1 detector quality — never read it, or present it, as tier-2/3
validation.

## The verdict rule

- **PASS** — Gate 0 passes **and** every *hard* floor in Gate 1 is met → release may
  proceed (`citevahti-release` gate 0). Publish all numbers, including the
  recall-at-precision, the full precision/recall operating-point curve, and the advisor
  figures, with N, κ, class counts, date, and version.
- **FAIL** — any hard floor missed → **no release.** File the gap, run an improvement
  cycle, re-measure on this same protocol.
- **Kill criterion** (`docs/BETA_TO_PRODUCTION.md`) — if mismatch-detector precision stays
  below its floor after **two** improvement cycles, the production push stops; CiteVahti
  reverts to internal-tool positioning. Pre-committed; not renegotiable mid-cycle.

## Change log (append-only — every threshold change, with reason and date)

| Date | Change | Reason | Made before or after a gated run? |
|---|---|---|---|
| 2026-07-07 | Initial proposed v0 (floors above) | First pre-registration; scaffolds the gate ahead of the first filled ledger | Before — no run has been scored |
| 2026-07-07 | Reframed to v0.1: precision is the sole gate; recall published as an operating-point curve rather than a soft target; added the "precision is a gate, sensitivity is a dial" inverted-U principle (over-flagging is worse than under-flagging; no universal sensitivity) | Maintainer steer — the right sensitivity is per-user/per-context; in-flow beats maximum recall | Before — no run has been scored |
