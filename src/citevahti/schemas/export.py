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


class ModelScore(BaseModel):
    """Per-model complementary-catch tally (ADR-0009 §3b — the local scoreboard
    precursor). A **catch** is a *validated divergence*: the model disagreed with the
    human and the human's adjudicated final matched the AI. Agreement earns nothing
    here — a model that never usefully diverges scores zero catches. Read-only,
    derived from existing rating records; nothing new is written."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    model_id: str
    model_snapshot: str
    ratings: int = 0
    concordant: int = 0
    discordant: int = 0
    catches: int = 0          # discordant AND resolved final == the AI value
    overruled: int = 0        # discordant, resolved, final != the AI value
    pending: int = 0          # discordant, not yet adjudicated
    abstained: int = 0
    catch_rate: Optional[float] = None   # catches / (catches + overruled), None if no resolved discordances


class ModelAdvice(BaseModel):
    """Which identifiable model to trust as an AI second opinion, from the live
    complementary-catch scoreboard (ADR-0009 §3b). Ranks by *complementary value*
    (validated catches over resolved divergences), never by agreement — a model
    that only echoes the human ranks nowhere. Stays silent on any model without
    enough resolved divergences to judge it (the evidence floor), and when a named
    model rates low it names a better-evidenced alternative. Read-only; a derived
    view over existing rating records that writes nothing."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    ranked: list[ModelScore] = Field(default_factory=list)   # well-evidenced, best complementary value first
    recommended: Optional[str] = None        # "model_id (snapshot)" of the top-ranked model, or None
    under_evidenced: list[str] = Field(default_factory=list)  # models below the floor — no opinion yet
    asked_about: Optional[str] = None        # the model_id queried, if any
    asked_catch_rate: Optional[float] = None  # its aggregate catch-rate across snapshots, if resolved
    suggestion: Optional[str] = None         # switch advice when the queried model rates low
    min_resolved: int = 0                    # resolved-divergence floor to be ranked at all
    low_catch_rate: float = 0.0              # at/below this (with enough evidence) counts as "rates low"
    notes: list[str] = Field(default_factory=list)


class AgreementReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    filters: dict = Field(default_factory=dict)
    metrics: list[str] = Field(default_factory=list)
    grouped_by: list[str] = Field(default_factory=list)
    overall: AgreementCounts = Field(default_factory=AgreementCounts)
    groups: list[AgreementGroup] = Field(default_factory=list)
    model_scoreboard: list[ModelScore] = Field(default_factory=list)
    ai_provenance_summary: dict = Field(default_factory=dict)
    method_transparency_markdown: str = ""
    formats_written: list[str] = Field(default_factory=list)
    output_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None
