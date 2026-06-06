"""Frame-level validators: scheme/unit/subject keying (Patch 4) and value vocab."""

from __future__ import annotations

from ..schemas.frame import Frame, Scheme
from ..schemas.rating import Subject
from .errors import FrameError


def validate_subject_for_scheme(frame: Frame, scheme_id: str, subject: Subject) -> Scheme:
    """Validate that ``subject`` is a well-formed key for ``scheme_id`` in ``frame``.

    Canonical units (Patch 4):
      - unit ``outcome``          -> outcome_id required (study_id absent)
      - unit ``study``            -> study_id required  (outcome_id absent)
      - unit ``study_x_outcome``  -> study_id + outcome_id required
    Referenced ids must exist in the frame. ``domain_id`` is permitted only when
    the scheme declares domains.
    """
    scheme = frame.get_scheme(scheme_id)
    if scheme is None:
        raise FrameError(f"scheme {scheme_id!r} is not defined on frame {frame.frame_id!r}")

    has_outcome = subject.outcome_id is not None
    has_study = subject.study_id is not None

    if scheme.unit == "outcome":
        if not has_outcome or has_study:
            raise FrameError("GRADE/outcome scheme requires exactly outcome_id (no study_id)")
    elif scheme.unit == "study":
        if not has_study or has_outcome:
            raise FrameError("study-level scheme requires exactly study_id (no outcome_id)")
    elif scheme.unit == "study_x_outcome":
        if not (has_study and has_outcome):
            raise FrameError("study_x_outcome scheme requires both study_id and outcome_id")

    if has_outcome and not frame.has_outcome(subject.outcome_id):  # type: ignore[arg-type]
        raise FrameError(f"outcome_id {subject.outcome_id!r} not in frame {frame.frame_id!r}")
    if has_study and not frame.has_study(subject.study_id):  # type: ignore[arg-type]
        raise FrameError(f"study_id {subject.study_id!r} not in frame {frame.frame_id!r}")

    if subject.domain_id is not None:
        domain_ids = {d.domain_id for d in (scheme.domains or [])}
        if subject.domain_id not in domain_ids:
            raise FrameError(
                f"domain_id {subject.domain_id!r} not declared on scheme {scheme_id!r}"
            )
    return scheme


def validate_value_in_scheme(scheme: Scheme, value: str) -> None:
    """Raise unless ``value`` is an exact level value of ``scheme``."""
    if value not in scheme.level_values():
        raise FrameError(
            f"value {value!r} is not a level of scheme {scheme.scheme_id!r}; "
            f"allowed: {sorted(scheme.level_values())}"
        )
