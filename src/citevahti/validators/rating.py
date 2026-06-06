"""The rating-record validity invariants (Patch 1 hardening + Patch 9).

These are the system's load-bearing guarantees:
  * AI never becomes the final value automatically or silently.
  * human_rating / ai_rating / comparison / adjudication are distinct fields.
  * a locked human value is never overwritten.
  * a discordant comparison never reaches a final value without 'adjudicated'.
  * a concordant value is locked in only via 'accepted', equal to the human value.
  * ai_abstained / human_only are never counted as human-AI agreement.
  * every AI rating carries complete provenance with a pinned model.
"""

from __future__ import annotations

from typing import Optional

from .. import PENDING_MODEL_ID, PENDING_MODEL_SNAPSHOT
from ..schemas.frame import Frame
from ..schemas.rating import RatingRecord
from .errors import HumanValueLockedError, RatingValidityError
from .frame import validate_subject_for_scheme, validate_value_in_scheme


def is_agreement_countable(record: RatingRecord) -> bool:
    """True only for concordant/discordant; abstention/human-only never count."""
    return record.comparison.status in ("concordant", "discordant")


def _validate_ai_provenance(record: RatingRecord) -> None:
    ai = record.ai_rating
    if ai is None:
        return
    p = ai.provenance
    required = {
        "provider": p.provider,
        "model_id": p.model_id,
        "model_snapshot": p.model_snapshot,
        "prompt_template_version": p.prompt_template_version,
        "prompt_hash": p.prompt_hash,
        "config_hash": p.config_hash,
        "rated_at": p.rated_at,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RatingValidityError(f"AI rating missing provenance fields: {missing}")
    if p.model_id == PENDING_MODEL_ID or p.model_snapshot == PENDING_MODEL_SNAPSHOT:
        raise RatingValidityError("AI rating carries an unpinned (PENDING) model")
    if ai.abstained and ai.value is not None:
        raise RatingValidityError("an abstained AI rating must have value=None")
    if not ai.abstained and ai.value is None:
        raise RatingValidityError("a non-abstained AI rating must carry a value")


def validate_final_value(record: RatingRecord) -> None:
    """Enforce the comparison/final-value invariant (Patch 9)."""
    comp = record.comparison
    adj = record.adjudication
    human_value = record.human_rating.value if record.human_rating else None
    ai_value = record.ai_rating.value if record.ai_rating else None

    # An event without a final value is meaningless.
    if adj.event is not None and adj.final_value is None:
        raise RatingValidityError("adjudication.event set without a final_value")

    if adj.final_value is None:
        return  # nothing locked in yet

    # A final value can never appear without an explicit adjudication event:
    # this is what prevents the AI value silently becoming final.
    if adj.event is None:
        raise RatingValidityError("final_value requires an adjudication event")

    if adj.event == "accepted":
        # 'accepted' applies only to a concordance and locks in the human value.
        if comp.status != "concordant":
            raise RatingValidityError("'accepted' is only valid for a concordant comparison")
        if human_value is None or adj.final_value != human_value:
            raise RatingValidityError(
                "an 'accepted' final_value must equal the locked human value"
            )

    if adj.event == "adjudicated":
        if not adj.decided_by:
            raise RatingValidityError("'adjudicated' requires adjudication.decided_by")

    # A discordance can never be locked in by mere acceptance.
    if comp.status == "discordant" and adj.event != "adjudicated":
        raise RatingValidityError("a discordant comparison requires an 'adjudicated' event")

    # Defense in depth: the AI value may only equal the final value when a human
    # explicitly adjudicated it. It can never arrive via 'accepted' (which is
    # pinned to the human value above).
    if (
        ai_value is not None
        and adj.final_value == ai_value
        and adj.final_value != human_value
        and adj.event != "adjudicated"
    ):
        raise RatingValidityError("final_value must not be sourced from ai_rating.value")


def validate_rating_record(
    record: RatingRecord, frame: Optional[Frame] = None
) -> None:
    """Run all structural + cross-field invariants on a rating record.

    When ``frame`` is supplied, subject keying and value vocabulary are checked
    against the frame's scheme too.
    """
    if frame is not None:
        if record.frame_id != frame.frame_id:
            raise RatingValidityError("record.frame_id does not match the provided frame")
        if record.frame_version != frame.frame_version:
            raise RatingValidityError(
                "record.frame_version does not match the provided frame"
            )
        scheme = validate_subject_for_scheme(frame, record.scheme_id, record.subject)
        if record.human_rating and record.human_rating.value is not None:
            validate_value_in_scheme(scheme, record.human_rating.value)
        if record.ai_rating and record.ai_rating.value is not None:
            validate_value_in_scheme(scheme, record.ai_rating.value)
        if record.adjudication.final_value is not None:
            validate_value_in_scheme(scheme, record.adjudication.final_value)

    _validate_ai_provenance(record)
    validate_final_value(record)


def assert_human_value_unchanged(
    existing: RatingRecord, incoming: RatingRecord
) -> None:
    """Guard a locked human value against overwrite on re-save.

    Once committed and locked, ``human_rating.value`` may never change.
    """
    old = existing.human_rating
    new = incoming.human_rating
    if old is None or not old.locked:
        return
    if new is None:
        raise HumanValueLockedError("cannot drop a locked human_rating on re-save")
    if new.value != old.value:
        raise HumanValueLockedError(
            f"locked human value {old.value!r} cannot be overwritten with {new.value!r}"
        )
