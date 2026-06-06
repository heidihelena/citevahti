"""Typed validation errors. Each maps to a stable ``ToolError.code``."""

from __future__ import annotations


class ValidationError(Exception):
    """Base class for CiteVahti validation failures."""

    code = "validation_error"


class ModelNotPinnedError(ValidationError):
    """The AI model pin is still a PENDING sentinel (Patch 1)."""

    code = "model_not_pinned"


class TaskNotAllowedError(ValidationError):
    """A task is not in the allowed rating/assist task set (Patch 2)."""

    code = "task_not_allowed"


class FrameError(ValidationError):
    """A subject key or value is invalid for the scheme/frame (Patch 4)."""

    code = "frame_error"


class RatingValidityError(ValidationError):
    """A rating record violates the hardening invariants (Patch 1 / Patch 9)."""

    code = "rating_invalid"


class HumanValueLockedError(ValidationError):
    """An attempt to overwrite a locked, committed human value."""

    code = "human_value_locked"
