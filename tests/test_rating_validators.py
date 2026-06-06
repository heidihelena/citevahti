"""The rating-record validity invariants (Patch 1 hardening + Patch 9)."""

import pytest

from citevahti.validators.errors import RatingValidityError
from citevahti.validators.rating import (
    is_agreement_countable,
    validate_rating_record,
)

from conftest import make_ai_provenance, make_grade_rating
from citevahti.schemas.rating import AIRating


def test_distinct_fields_exist():
    rec = make_grade_rating()
    # the four hardening fields are structurally distinct
    assert rec.human_rating.value == "Moderate"
    assert rec.ai_rating.value == "Moderate"
    assert hasattr(rec.comparison, "status")
    assert hasattr(rec.adjudication, "final_value")


def test_concordant_accepted_is_valid():
    rec = make_grade_rating(human_value="Moderate", ai_value="Moderate",
                            status="concordant", final_value="Moderate", event="accepted")
    validate_rating_record(rec)


def test_final_value_without_event_is_invalid():
    # the AI value silently becoming final must be impossible
    rec = make_grade_rating(status="concordant", final_value="Moderate", event=None)
    with pytest.raises(RatingValidityError):
        validate_rating_record(rec)


def test_discordant_cannot_be_accepted():
    rec = make_grade_rating(human_value="Low", ai_value="High",
                            status="discordant", final_value="Low", event="accepted")
    with pytest.raises(RatingValidityError):
        validate_rating_record(rec)


def test_discordant_requires_adjudication_for_final():
    # adjudicated by a human is the only path
    ok = make_grade_rating(human_value="Low", ai_value="High", status="discordant",
                           final_value="Low", event="adjudicated", decided_by="panel")
    validate_rating_record(ok)
    bad = make_grade_rating(human_value="Low", ai_value="High", status="discordant",
                            final_value="High", event="adjudicated")  # no decided_by
    with pytest.raises(RatingValidityError):
        validate_rating_record(bad)


def test_accepted_final_must_equal_human_value():
    rec = make_grade_rating(human_value="Moderate", ai_value="Moderate",
                            status="concordant", final_value="High", event="accepted")
    with pytest.raises(RatingValidityError):
        validate_rating_record(rec)


def test_ai_value_cannot_be_final_without_human_decision():
    # status concordant but final equals AI while != human, no event -> invalid
    rec = make_grade_rating(human_value="Low", ai_value="High",
                            status="discordant", final_value="High", event=None)
    with pytest.raises(RatingValidityError):
        validate_rating_record(rec)


def test_ai_provenance_required_and_pinned():
    rec = make_grade_rating()
    rec.ai_rating = AIRating(value="Moderate",
                             provenance=make_ai_provenance(model_id="PENDING_USER_APPROVAL"))
    with pytest.raises(RatingValidityError):
        validate_rating_record(rec)


def test_abstention_and_human_only_not_countable():
    abst = make_grade_rating(ai_abstained=True, ai_value=None, status="ai_abstained")
    human_only = make_grade_rating(ai_value=None, status="human_only")
    assert is_agreement_countable(abst) is False
    assert is_agreement_countable(human_only) is False
    assert is_agreement_countable(make_grade_rating(status="concordant")) is True
    assert is_agreement_countable(make_grade_rating(status="discordant")) is True


def test_abstained_ai_must_have_no_value():
    rec = make_grade_rating(status="ai_abstained")
    rec.ai_rating = AIRating(value="Moderate", abstained=True, provenance=make_ai_provenance())
    with pytest.raises(RatingValidityError):
        validate_rating_record(rec)


def test_frame_keying_checked_when_frame_supplied(frame):
    rec = make_grade_rating(status="concordant")
    validate_rating_record(rec, frame=frame)
    rec.frame_version = "2.0.0"  # mismatch
    with pytest.raises(RatingValidityError):
        validate_rating_record(rec, frame=frame)
