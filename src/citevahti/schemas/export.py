"""Schemas for evidence_export and agreement_report (read-only reporting)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import Provenance


# ---- evidence_export -------------------------------------------------------
class EvidenceExportReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    selection: dict = Field(default_factory=dict)
    full_map: bool = False
    selected_node_count: int = 0
    selected_citekey_count: int = 0
    selected_citekeys: list[str] = Field(default_factory=list)
    include_provenance: bool = False
    include_ai_values: bool = False
    formats_written: list[str] = Field(default_factory=list)
    output_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None


# ---- agreement_report ------------------------------------------------------
class AgreementCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comparable_pairs: int = 0
    agreements: int = 0
    disagreements: int = 0
    human_only: int = 0
    ai_abstained: int = 0
    adjudicated: int = 0
    pending_adjudication: int = 0
    final_value_categories: dict = Field(default_factory=dict)


class AgreementGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: dict = Field(default_factory=dict)
    scheme_id: Optional[str] = None
    counts: AgreementCounts = Field(default_factory=AgreementCounts)
    metrics: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AgreementReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    filters: dict = Field(default_factory=dict)
    metrics: list[str] = Field(default_factory=list)
    grouped_by: list[str] = Field(default_factory=list)
    overall: AgreementCounts = Field(default_factory=AgreementCounts)
    groups: list[AgreementGroup] = Field(default_factory=list)
    ai_provenance_summary: dict = Field(default_factory=dict)
    method_transparency_markdown: str = ""
    formats_written: list[str] = Field(default_factory=list)
    output_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None
