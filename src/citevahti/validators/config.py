"""Config-level validators: AI model pin (Patch 1) and task authorization (Patch 2)."""

from __future__ import annotations

from ..schemas.config import AIProvenanceConfig
from .errors import ModelNotPinnedError, TaskNotAllowedError


def require_model_pinned(ai: AIProvenanceConfig) -> None:
    """Raise unless an explicit model id + snapshot are configured.

    Called before any AI rating task runs. The defaults are PENDING sentinels;
    the user must supply the model before ``rating_run_ai`` will execute.
    """
    if not ai.is_model_pinned():
        raise ModelNotPinnedError(
            "AI model is not pinned: set ai_provenance.model_id and "
            "ai_provenance.model_snapshot in config.json before running AI ratings."
        )


def authorize_rating_task(ai: AIProvenanceConfig, task_type: str) -> None:
    """Raise unless ``task_type`` is an allowed AI rating task.

    ``screen_vote`` is only permitted when ``screen_vote_enabled`` is true, and
    even then it feeds agreement metrics only -- never an inclusion decision.
    Assist tasks (e.g. ``claim_check``) are NOT rating tasks (Patch 2).
    """
    allowed = ai.effective_rating_tasks()
    if task_type not in allowed:
        if task_type in ai.allowed_assist_tasks:
            raise TaskNotAllowedError(
                f"{task_type!r} is an assist task, not a rating task; "
                "use the assist surface, not rating_run_ai."
            )
        if task_type in ai.optional_rating_tasks and not ai.screen_vote_enabled:
            raise TaskNotAllowedError(
                f"{task_type!r} is optional and disabled; enable "
                "ai_provenance.screen_vote_enabled to use it (metrics only)."
            )
        raise TaskNotAllowedError(
            f"{task_type!r} is not an allowed rating task; allowed: {sorted(allowed)}"
        )


def authorize_assist_task(ai: AIProvenanceConfig, task_type: str) -> None:
    """Raise unless ``task_type`` is an allowed AI assist task."""
    if task_type not in ai.allowed_assist_tasks:
        raise TaskNotAllowedError(
            f"{task_type!r} is not an allowed assist task; "
            f"allowed: {sorted(ai.allowed_assist_tasks)}"
        )
