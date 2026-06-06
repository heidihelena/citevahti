"""DecisionService (ADR-0001 step 4): the human-owned terminal judgment.

Records one final decision per (claim, candidate): accept / reject /
needs_second_review / accepted_with_caution. When it rests on a claim-support
rating, it derives the final support status + human/AI agreement from that
rating and refuses to finalize on an *unresolved* discordance. The mission
invariant ('accept' only on a supporting status) is enforced at the store.
"""

from __future__ import annotations

from typing import Optional

from .. import __version__
from ..schemas.common import Provenance
from ..schemas.decision import FinalDecision
from ..util import config_hash, utc_now_iso
from ..validators.decision import DecisionError


class DecisionService:
    def __init__(self, store) -> None:
        self.store = store

    def _require_candidate(self, claim_id: str, candidate_id: str):
        self.store.load_claim(claim_id)              # raises StateError if unknown
        cc = self.store.load_candidates(claim_id)     # raises StateError if none linked
        for c in cc.candidates:
            if c.candidate_id == candidate_id:
                return c
        raise DecisionError(f"candidate {candidate_id!r} is not linked to claim {claim_id!r}")

    @staticmethod
    def _derive(rating):
        """Return (final_support_status, agreement_status, resolved)."""
        adj = rating.adjudication
        status = rating.comparison.status
        hv = rating.human_rating.value if rating.human_rating else None
        if adj.final_value is not None:
            return adj.final_value, status, True
        # no disagreement to resolve: the human value stands
        if status in ("concordant", "human_only", "ai_abstained") and hv is not None:
            return hv, status, True
        # discordant + unadjudicated (or no human yet): not resolved
        return None, status, False

    def decide(self, claim_id: str, candidate_id: str, final_decision: str,
               decision_reason: str, *, rating_id: Optional[str] = None,
               decided_by: str = "human") -> FinalDecision:
        self._require_candidate(claim_id, candidate_id)

        support_status = agreement = None
        if rating_id is not None:
            rating = self.store.load_support_rating(rating_id)
            if rating.claim_id != claim_id or rating.candidate_id != candidate_id:
                raise DecisionError(
                    f"rating {rating_id!r} is for a different (claim, candidate) pair")
            support_status, agreement, resolved = self._derive(rating)
            # Never finalize accept/reject on an unresolved disagreement.
            if not resolved and final_decision != "needs_second_review":
                raise DecisionError(
                    "the claim-support rating is a discordance that has not been adjudicated; "
                    "adjudicate it first, or record 'needs_second_review'")

        record = FinalDecision(
            decision_id=f"dec-{candidate_id}", claim_id=claim_id, candidate_id=candidate_id,
            rating_id=rating_id, final_support_status=support_status,
            final_decision=final_decision, agreement_status=agreement,
            decided_by=decided_by, decision_reason=decision_reason, created_at=utc_now_iso(),
            provenance=Provenance(
                tool="final_decision", tool_version=__version__, ran_at=utc_now_iso(),
                config_hash=config_hash({"claim_id": claim_id, "candidate_id": candidate_id}),
                sources=([{"kind": "claim_support", "detail": rating_id}] if rating_id else [])))
        return self.store.save_decision(record)

    def get(self, candidate_id: str) -> FinalDecision:
        return self.store.load_decision(f"dec-{candidate_id}")

    def list_for_claim(self, claim_id: str) -> list[FinalDecision]:
        out = []
        for did in self.store.list_decisions():
            rec = self.store.load_decision(did)
            if rec.claim_id == claim_id:
                out.append(rec)
        return out
