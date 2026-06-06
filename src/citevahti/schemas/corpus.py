"""Corpus-diff report schema."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import Provenance


class StudyChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str                          # citekey when available, else item key
    zotero_key: Optional[str] = None
    citekey: Optional[str] = None
    change_types: list[str] = Field(default_factory=list)  # metadata/doi_pmid/title_year/fulltext/attachment


class AffectedRefs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attachments: list[str] = Field(default_factory=list)
    ratings: list[str] = Field(default_factory=list)
    recommendation_nodes: list[str] = Field(default_factory=list)
    outcome_nodes: list[str] = Field(default_factory=list)


class CorpusDiffReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_snapshot_id: str
    to_snapshot_id: str               # "current" when comparing to live corpus
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[StudyChange] = Field(default_factory=list)
    stale_candidates: list[str] = Field(default_factory=list)
    affected: AffectedRefs = Field(default_factory=AffectedRefs)
    mark_stale: bool = False
    stale_flags_added: list[str] = Field(default_factory=list)
    status: str = "ok"
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None
