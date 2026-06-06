"""Result envelopes for dual-rating, assess, retraction, and PRISMA tools."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import Provenance

# ---- dual-rating -----------------------------------------------------------
ComparisonOutcome = Literal["accepted", "needs_adjudication", "ai_abstained", "human_only"]


class RatingComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating_id: str
    status: Optional[str] = None          # comparison.status (concordant/discordant/...)
    outcome: ComparisonOutcome
    needs_adjudication: bool = False
    human_value: Optional[str] = None
    ai_value: Optional[str] = None
    final_value: Optional[str] = None
    agreement_countable: bool = False


# ---- assess ----------------------------------------------------------------
class AssessmentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_id: str
    scheme_id: str
    scheme_kind: str
    subject: dict
    human_value: str
    reasons: list[str] = Field(default_factory=list)
    rationale: Optional[str] = None
    status: Literal["human_only", "dual_rating_started"] = "human_only"
    attachment_id: Optional[str] = None
    rating_id: Optional[str] = None
    stale_flags: list[str] = Field(default_factory=list)
    tag_mirror_status: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None


# ---- retraction ------------------------------------------------------------
class RetractedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    citekey: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    status: str = "retracted"
    source: Optional[str] = None
    notice_url: Optional[str] = None


class AffectedRefs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attachments: list[str] = Field(default_factory=list)
    ratings: list[str] = Field(default_factory=list)
    recommendation_nodes: list[str] = Field(default_factory=list)
    outcome_nodes: list[str] = Field(default_factory=list)


class RetractionScanReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scanned_count: int = 0
    retracted: list[RetractedItem] = Field(default_factory=list)
    affected: AffectedRefs = Field(default_factory=AffectedRefs)
    mark_stale: bool = False
    retraction_flags_added: list[str] = Field(default_factory=list)
    staleness_flags_added: list[str] = Field(default_factory=list)
    status: str = "ok"
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None
