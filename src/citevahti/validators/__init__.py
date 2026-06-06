"""Binding validators. These are asserted by tests, not merely documented."""

from .config import (
    authorize_assist_task,
    authorize_rating_task,
    require_model_pinned,
)
from .errors import (
    FrameError,
    HumanValueLockedError,
    ModelNotPinnedError,
    RatingValidityError,
    TaskNotAllowedError,
    ValidationError,
)
from .frame import (
    validate_subject_for_scheme,
    validate_value_in_scheme,
)
from .probe import ProbeValidationError, assert_valid_probed_version
from .rating import (
    assert_human_value_unchanged,
    is_agreement_countable,
    validate_final_value,
    validate_rating_record,
)

__all__ = [
    "ValidationError",
    "ModelNotPinnedError",
    "TaskNotAllowedError",
    "FrameError",
    "RatingValidityError",
    "HumanValueLockedError",
    "require_model_pinned",
    "authorize_rating_task",
    "authorize_assist_task",
    "validate_subject_for_scheme",
    "validate_value_in_scheme",
    "ProbeValidationError",
    "assert_valid_probed_version",
    "validate_rating_record",
    "validate_final_value",
    "assert_human_value_unchanged",
    "is_agreement_countable",
]
