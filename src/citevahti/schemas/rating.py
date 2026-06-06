"""The rating record (one subject, one scheme).

Hardening Patch 1: ``human_rating.value``, ``ai_rating.value``,
``comparison.status`` and ``adjudication.final_value`` are DISTINCT fields. The
record judges exactly one subject under one scheme. Actors live inside their
blocks (Patch 5): ``human_rating.committed_by``, ``ai_rating.provenance``,
``adjudication.decided_by`` -- there is no top-level ``actor_id``. Multiple human
raters are linked via ``rating_set_id``.

Structural invariants are declared here; the cross-field validity invariants
(final never silently = AI; discordant never auto-accepted; human value never
overwritten; AI provenance present) are enforced in ``citevahti.validators``.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import PassageRef

ComparisonStatus = Literal["concordant", "discordant", "ai_abstained", "human_only"]
AdjudicationEvent = Literal["accepted", "adjudicated"]
AccessEvent = Literal["seal", "reveal", "view", "commit"]


class HumanRating(BaseModel):
    """Locked after commit and never overwritten (enforced at the store)."""

    model_config = ConfigDict(extra="forbid")
    value: Optional[str] = None
    committed_at: str
    committed_by: str
    notes: Optional[str] = None
    rationale: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    source_passages: list[PassageRef] = Field(default_factory=list)
    locked: bool = True


class AIProvenance(BaseModel):
    """Full provenance required on every AI rating (Patch 1)."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    provider: str
    model_id: str
    model_snapshot: str
    prompt_template_version: str
    prompt_hash: str
    config_hash: str
    rated_at: str


class AIRating(BaseModel):
    """Blind, independent second rating. Can NEVER become final automatically."""

    model_config = ConfigDict(extra="forbid")
    value: Optional[str] = None  # None when abstained
    abstained: bool = False
    confidence: Optional[float] = None  # calibrated 0..1
    supporting_passages: list[PassageRef] = Field(default_factory=list)
    domain_reasoning: Optional[str] = None
    task_type: Optional[str] = None  # e.g. "assess" / "extract" / "screen_vote"
    provenance: AIProvenance


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Optional[ComparisonStatus] = None
    computed_at: Optional[str] = None


class Adjudication(BaseModel):
    """The ONLY path to a final value on a discordance.

    ``final_value`` is always human/panel-sourced.
    """

    model_config = ConfigDict(extra="forbid")
    final_value: Optional[str] = None
    event: Optional[AdjudicationEvent] = None
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    rationale: Optional[str] = None


class AccessLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ts: str
    actor: str
    event: AccessEvent
    target: Optional[Literal["human", "ai", "other_rater"]] = None


class Blinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = "human_first_ai_blind"
    access_log: list[AccessLogEntry] = Field(default_factory=list)
    independent: bool = True


class Subject(BaseModel):
    """Scheme-dependent canonical subject key (Patch 4).

    - GRADE (unit ``outcome``)          : outcome_id
    - RoB study (unit ``study``)        : study_id
    - RoB study x outcome               : study_id + outcome_id
    ``domain_id`` is set for RoB domain-level records.
    """

    model_config = ConfigDict(extra="forbid")
    outcome_id: Optional[str] = None
    study_id: Optional[str] = None
    domain_id: Optional[str] = None


class RatingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating_id: str
    rating_set_id: Optional[str] = None  # links multiple human raters (Patch 5)
    frame_id: str
    frame_version: str
    scheme_id: str
    subject: Subject
    human_rating: Optional[HumanRating] = None
    ai_rating: Optional[AIRating] = None
    comparison: Comparison = Field(default_factory=Comparison)
    adjudication: Adjudication = Field(default_factory=Adjudication)
    blinding: Blinding = Field(default_factory=Blinding)
