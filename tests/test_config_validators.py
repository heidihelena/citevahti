"""Config validators: model pin (Patch 1) + rating/assist task split (Patch 2)."""

import pytest

from citevahti.schemas.config import Config
from citevahti.validators import (
    authorize_assist_task,
    authorize_rating_task,
    require_model_pinned,
)
from citevahti.validators.errors import ModelNotPinnedError, TaskNotAllowedError


def test_model_pin_required_by_default():
    cfg = Config.default()
    with pytest.raises(ModelNotPinnedError):
        require_model_pinned(cfg.ai_provenance)
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    require_model_pinned(cfg.ai_provenance)  # no raise


def test_rating_tasks_vs_assist_tasks():
    ai = Config.default().ai_provenance
    authorize_rating_task(ai, "assess")
    authorize_rating_task(ai, "extract")
    # claim_check is an ASSIST task, not a rating task
    with pytest.raises(TaskNotAllowedError):
        authorize_rating_task(ai, "claim_check")
    authorize_assist_task(ai, "claim_check")  # ok on the assist surface


def test_screen_vote_disabled_by_default():
    ai = Config.default().ai_provenance
    assert ai.screen_vote_enabled is False
    with pytest.raises(TaskNotAllowedError):
        authorize_rating_task(ai, "screen_vote")
    ai.screen_vote_enabled = True
    authorize_rating_task(ai, "screen_vote")  # now allowed (metrics only)


def test_rating_run_ai_guard_order():
    # the engine runs these guards (model pin, then task auth) before any AI behavior
    cfg = Config.default()
    with pytest.raises(ModelNotPinnedError):
        require_model_pinned(cfg.ai_provenance)
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    require_model_pinned(cfg.ai_provenance)             # now pinned
    with pytest.raises(TaskNotAllowedError):
        authorize_rating_task(cfg.ai_provenance, "claim_check")  # assist task, not rating
    authorize_rating_task(cfg.ai_provenance, "assess")
