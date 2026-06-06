"""Frame validators: scheme/unit subject keying (Patch 4); ROBINS-I (Patch 8)."""

import pytest

from citevahti.schemas.rating import Subject
from citevahti.validators.errors import FrameError
from citevahti.validators.frame import validate_subject_for_scheme, validate_value_in_scheme


def test_grade_requires_outcome_only(frame):
    validate_subject_for_scheme(frame, "grade_certainty", Subject(outcome_id="o_mortality"))
    with pytest.raises(FrameError):
        validate_subject_for_scheme(frame, "grade_certainty", Subject(study_id="s_smith2020"))
    with pytest.raises(FrameError):
        validate_subject_for_scheme(
            frame, "grade_certainty",
            Subject(outcome_id="o_mortality", study_id="s_smith2020"),
        )


def test_rob_study_requires_study_only(frame):
    validate_subject_for_scheme(frame, "rob2", Subject(study_id="s_smith2020"))
    with pytest.raises(FrameError):
        validate_subject_for_scheme(frame, "rob2", Subject(outcome_id="o_mortality"))


def test_unknown_ids_rejected(frame):
    with pytest.raises(FrameError):
        validate_subject_for_scheme(frame, "grade_certainty", Subject(outcome_id="nope"))
    with pytest.raises(FrameError):
        validate_subject_for_scheme(frame, "missing_scheme", Subject(outcome_id="o_mortality"))


def test_domain_must_be_declared(frame):
    validate_subject_for_scheme(frame, "rob2", Subject(study_id="s_smith2020", domain_id="d1"))
    with pytest.raises(FrameError):
        validate_subject_for_scheme(frame, "rob2",
                                    Subject(study_id="s_smith2020", domain_id="dX"))


def test_value_must_be_in_scheme(frame):
    grade = frame.get_scheme("grade_certainty")
    validate_value_in_scheme(grade, "Very Low")
    with pytest.raises(FrameError):
        validate_value_in_scheme(grade, "Very low")  # wrong case (Patch 10 exactness)


def test_robins_no_information_is_missing_like(frame):
    robins = frame.get_scheme("robins_i")
    no_info = next(lvl for lvl in robins.levels if lvl.value == "No information")
    assert no_info.missing_like is True and no_info.ordinal is None
    # excluded from the ordered/ordinal levels used by ordinal-aware statistics
    assert "No information" not in {lvl.value for lvl in robins.ordinal_levels()}
