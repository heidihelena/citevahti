"""Organized-panel aggregate (ADR-0008, the review/guideline tiers): "X of N support".

The spine already records one claim-support rating per (claim, candidate, rater): `support_start`
mints a record, `support_commit_human` stamps the rater (`committed_by`) and value, and
`rating_set_id` links a panel. This module adds **no new rating engine** — it *aggregates* those
human ratings into a panel summary: how many of N independent human reviewers support the claim,
the value distribution, the raw inter-rater agreement, and the ADR-0008 confidence tier.

The AI second opinion is **not** a panel member — only human ratings are counted, so N is never
inflated. Raters are distinguished by `committed_by`, so a real panel must give each reviewer a
distinct id (e.g. `--committed-by reviewer-2`); ratings left as the default `human` collapse to
one rater.
"""

from __future__ import annotations

from collections import Counter

from ..state.store import StateError
from .support import rating_preference_key

# Support-positive values (the cited paper supports the claim AS MADE). `overstated` is an
# overclaim (the paper supports a *weaker* claim), so it is NOT counted as support.
SUPPORTING = ("directly_supports", "partially_supports", "indirectly_supports")


def tier_of(n: int) -> str:
    """ADR-0008 ladder by independent human-rater count: 1 individual · 2–7 review · 8+ guideline."""
    if n >= 8:
        return "guideline"
    if n >= 2:
        return "review"
    if n == 1:
        return "individual"
    return "none"


def _human_ratings_by_rater(store, claim_id: str, candidate_id: str) -> dict:
    """The most-advanced committed human rating per distinct rater (`committed_by`) for the pair."""
    best: dict = {}
    for rid in store.list_support_ratings():
        rec = store.load_support_rating(rid)
        if rec.claim_id != claim_id or rec.candidate_id != candidate_id:
            continue
        h = rec.human_rating
        if h is None or h.value is None:
            continue
        rater = h.committed_by or "human"
        if rater not in best or rating_preference_key(rec) > rating_preference_key(best[rater]):
            best[rater] = rec
    return best


def panel_summary(store, claim_id: str, candidate_id: str) -> dict:
    """Aggregate the human panel for one (claim, candidate): X of N support + tier + distribution."""
    by_rater = _human_ratings_by_rater(store, claim_id, candidate_id)
    values = {rater: rec.human_rating.value for rater, rec in by_rater.items()}
    n = len(values)
    support_x = sum(1 for v in values.values() if v in SUPPORTING)
    dist = dict(Counter(values.values()))
    modal = max(dist.values()) if dist else 0
    return {
        "claim_id": claim_id, "candidate_id": candidate_id,
        "n_raters": n, "support_count": support_x,
        "headline": f"{support_x} of {n} support",
        "tier": tier_of(n),
        "distribution": dist,
        "raters": [{"by": r, "value": v} for r, v in sorted(values.items())],
        "raw_agreement": round(modal / n, 2) if n else None,
    }


def claim_panel_summary(store, claim_id: str) -> dict:
    """Panel summary across all of a claim's candidates (the claim's tier = its widest panel)."""
    try:
        cands = store.load_candidates(claim_id).candidates
    except StateError:
        cands = []
    per = [panel_summary(store, claim_id, c.candidate_id) for c in cands]
    per = [p for p in per if p["n_raters"] > 0]
    n_max = max((p["n_raters"] for p in per), default=0)
    return {"claim_id": claim_id, "tier": tier_of(n_max), "candidates": per}
