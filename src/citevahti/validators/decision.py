"""Final-decision validators (ADR-0001 step 4).

The mission invariant: an 'accept' (or 'accepted_with_caution') may only rest on
a final support status that actually supports the claim. You cannot accept a
citation rated does_not_support / contradicts / unclear — that is exactly the
"cite the wrong paper" failure CiteVahti exists to prevent.
"""

from __future__ import annotations

from ..schemas.decision import FINAL_DECISIONS, SUPPORTING_VALUES, FinalDecision
from ..schemas.claim_support import SUPPORT_VALUES
from .errors import ValidationError


class DecisionError(ValidationError):
    code = "decision_invalid"


def validate_final_decision(record: FinalDecision, *, require_audit: bool = False) -> None:
    if not record.claim_id or not record.candidate_id:
        raise DecisionError("a final decision must reference claim_id + candidate_id")
    if record.final_decision not in FINAL_DECISIONS:
        raise DecisionError(f"unsupported final_decision {record.final_decision!r}")
    if not (record.decision_reason or "").strip():
        raise DecisionError("a final decision must record a decision_reason")
    if (record.final_support_status is not None
            and record.final_support_status not in SUPPORT_VALUES):
        raise DecisionError(
            f"final_support_status {record.final_support_status!r} not in the vocabulary")
    # The mission invariant.
    if record.final_decision in ("accept", "accepted_with_caution"):
        if record.final_support_status is None:
            raise DecisionError(
                f"'{record.final_decision}' requires a resolved final_support_status "
                "(rate + adjudicate the claim-support first)")
        if record.final_support_status not in SUPPORTING_VALUES:
            raise DecisionError(
                f"cannot {record.final_decision!r} a candidate whose final support is "
                f"{record.final_support_status!r}; only {SUPPORTING_VALUES} support the claim")
    if require_audit and not record.audit_event_id:
        raise DecisionError("final decision missing audit_event_id after write")
