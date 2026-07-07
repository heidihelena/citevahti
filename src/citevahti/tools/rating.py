"""Frame (GRADE-style) dual-rating operations (ADR-0010 PR 1f — ledger-write group).

The blinded human+AI rating engine for controlled-vocabulary frame assessments: start a
rating, commit the HUMAN value first, run the AI as a blinded independent second rater,
compare, and adjudicate a discordance. ``assess`` records a human-chosen controlled value
(it never computes, suggests, or pre-fills one).

Blinding is load-bearing (ADR-0001): the AI never sees the human value and its rating never
decides. That invariant lives in the ``rating`` service layer and the agent surface — these
are thin façade wrappers over ``RatingEngine`` and do not re-implement or relax it (guarded
by test_blinding_deterministic.py and the agent-surface blinding tests). Writes only to the
local, audited ledger.

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ..schemas.rating import Subject
from ._common import _open_store


def _rating_engine(root, ai_rater):
    from ..rating import RatingEngine
    return RatingEngine(_open_store(root), ai_rater=ai_rater)


def rating_start(frame_id: str, scheme_id: str, subject: Subject, domain_id: Optional[str] = None,
                 *, root: Optional[str] = None):
    return _rating_engine(root, None).rating_start(frame_id, scheme_id, subject, domain_id)


def rating_commit_human(rating_id: str, value: str, rationale: Optional[str] = None,
                        reasons: Optional[list[str]] = None, source_passages=None,
                        committed_by: str = "human", *, root: Optional[str] = None):
    return _rating_engine(root, None).rating_commit_human(
        rating_id, value, rationale=rationale, reasons=reasons, source_passages=source_passages,
        committed_by=committed_by)


def rating_run_ai(rating_id: str, task_type: str, *, root: Optional[str] = None, ai_rater=None):
    """Blind AI second rating. Refuses unallowed/assist tasks; requires a model pin."""
    return _rating_engine(root, ai_rater).rating_run_ai(rating_id, task_type)


def rating_compare(rating_id: str, *, root: Optional[str] = None):
    return _rating_engine(root, None).rating_compare(rating_id)


def rating_adjudicate(rating_id: str, final_value: str, rationale: str, decider: str = "human",
                      *, root: Optional[str] = None):
    return _rating_engine(root, None).rating_adjudicate(rating_id, final_value, rationale, decider)


def assess(frame_id: str, scheme_id: str, subject: Subject, human_value: str,
           reasons: Optional[list[str]] = None, rationale: Optional[str] = None,
           dual_rating: bool = False, tag_mirror: bool = False, *, root: Optional[str] = None,
           ai_rater=None):
    """Record a human-chosen controlled value. Never computes/suggests/pre-fills."""
    from ..assess import AssessmentService
    from ..rating import RatingEngine
    store = _open_store(root)
    engine = RatingEngine(store, ai_rater=ai_rater) if dual_rating else None
    return AssessmentService(store, engine).assess(
        frame_id, scheme_id, subject, human_value, reasons=reasons, rationale=rationale,
        dual_rating=dual_rating, tag_mirror=tag_mirror)
