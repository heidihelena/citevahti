"""Claim-support rating validators (ADR-0001, step 3).

Mirrors the study-quality engine's binding invariants for the (claim, candidate)
support dimension: AI is advisory and never final; a discordance needs human/panel
adjudication; the final value is never the AI value; the human value is locked.
"""

from __future__ import annotations

from ..schemas.claim_support import FIT_FIELDS, SUPPORT_VALUES, ClaimSupportRating
from .errors import HumanValueLockedError, ValidationError


class ClaimSupportError(ValidationError):
    code = "claim_support_invalid"


def _validate_fit(fit, who: str) -> None:
    for f in FIT_FIELDS:
        v = getattr(fit, f, None)
        if v is not None and v not in (0, 1, 2):
            raise ClaimSupportError(f"{who} {f}={v!r} must be 0, 1, or 2")


def _validate_ai(record: ClaimSupportRating) -> None:
    ai = record.ai_rating
    if ai is None:
        return
    if ai.provenance is None:
        raise ClaimSupportError("AI support rating missing provenance")
    # never an unpinned/placeholder model in a persisted rating
    if "PENDING" in (ai.provenance.model_id or "") or "PENDING" in (ai.provenance.model_snapshot or ""):
        raise ClaimSupportError("AI support rating carries an unpinned (PENDING) model")
    if ai.abstained and ai.value is not None:
        raise ClaimSupportError("an abstained AI rating must have value=None")
    if not ai.abstained and ai.value is None:
        raise ClaimSupportError("a non-abstained AI rating must carry a value")
    if ai.value is not None and ai.value not in SUPPORT_VALUES:
        raise ClaimSupportError(f"AI support value {ai.value!r} not in the controlled vocabulary")
    _validate_fit(ai.fit, "ai")


def _validate_final(record: ClaimSupportRating) -> None:
    adj = record.adjudication
    status = record.comparison.status
    if adj.event is not None and adj.final_value is None:
        raise ClaimSupportError("adjudication.event set without a final_value")
    if adj.final_value is None:
        return  # nothing locked in yet (a discordance may legitimately await adjudication)
    # final_value present:
    if adj.event is None:
        raise ClaimSupportError("final_value requires an adjudication event")
    if adj.final_value not in SUPPORT_VALUES:
        raise ClaimSupportError(f"final_value {adj.final_value!r} not in the controlled vocabulary")
    hv = record.human_rating.value if record.human_rating else None
    av = record.ai_rating.value if record.ai_rating else None
    if adj.event == "accepted":
        if status != "concordant":
            raise ClaimSupportError("'accepted' is only valid for a concordant comparison")
        if hv is None or adj.final_value != hv:
            raise ClaimSupportError("an 'accepted' final_value must equal the locked human value")
    if adj.event == "adjudicated" and not adj.decided_by:
        raise ClaimSupportError("'adjudicated' requires adjudication.decided_by")
    if status == "discordant" and adj.event != "adjudicated":
        raise ClaimSupportError("a discordant comparison requires an 'adjudicated' event")
    # The AI value may equal the final value ONLY when a human explicitly
    # adjudicated it -- never silently (e.g. via 'accepted').
    if (av is not None and adj.final_value == av and adj.final_value != hv
            and adj.event != "adjudicated"):
        raise ClaimSupportError("final_value must not be sourced from the AI value")


def validate_claim_support_record(record: ClaimSupportRating, *, require_audit: bool = False) -> None:
    if not record.claim_id or not record.candidate_id:
        raise ClaimSupportError("a claim-support rating must reference claim_id + candidate_id")
    if record.human_rating is not None:
        if record.human_rating.value is not None and record.human_rating.value not in SUPPORT_VALUES:
            raise ClaimSupportError(
                f"human support value {record.human_rating.value!r} not in the vocabulary")
        _validate_fit(record.human_rating.fit, "human")
    _validate_ai(record)
    _validate_final(record)
    if require_audit and not record.audit_event_id:
        raise ClaimSupportError("claim-support rating missing audit_event_id after write")


def assert_support_human_unchanged(existing: ClaimSupportRating,
                                   incoming: ClaimSupportRating) -> None:
    old = existing.human_rating
    new = incoming.human_rating
    if old is None or not old.locked:
        return
    if new is None:
        raise HumanValueLockedError("cannot drop a locked human support rating on re-save")
    if new.value != old.value:
        raise HumanValueLockedError(
            f"locked human support value {old.value!r} cannot be overwritten with {new.value!r}")
