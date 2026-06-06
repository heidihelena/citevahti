"""De-identified validation record (ADR-0001 step 6) — the reusable, privacy-bounded asset.

This is the *reusable* tier (ADR §7): it deliberately excludes sensitive user
content — no identity, no manuscript text, no Zotero keys, no project-internal
ids. It keeps only what makes a claim-paper rating reusable as a label:
claim_type, a one-way claim-text hash (and the claim text itself ONLY on a second
explicit opt-in), the public paper identifier (PMID/DOI), the AI/human/final
ratings, the PICO fit, agreement, and the study-type signal.

Records are append-only; corrections are appended, never edited in place. The
warehouse is opt-in and default-off, and can be purged per project (consent
withdrawal).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION


class ValidationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    record_id: str
    created_at: str
    # de-identified claim
    claim_type: Optional[str] = None
    claim_text_hash: str                       # one-way; always present
    claim_text: Optional[str] = None           # top-sensitivity tier; only with opt-in
    domain: Optional[str] = None
    # public paper identifiers (not sensitive)
    pmid: Optional[str] = None
    doi: Optional[str] = None
    study_type: Optional[str] = None           # evidence quality signal
    # the rating outcome (the label)
    ai_support_rating: Optional[str] = None
    ai_confidence: Optional[float] = None
    human_support_rating: Optional[str] = None
    final_support_status: Optional[str] = None
    final_decision: Optional[str] = None
    agreement_status: Optional[str] = None
    population_fit: Optional[int] = None
    intervention_fit: Optional[int] = None
    outcome_fit: Optional[int] = None
    claim_fit: Optional[int] = None
    rating_schema_version: str = SCHEMA_VERSION


class WarehouseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    include_claim_text: bool = False
    record_count: int = 0
    emitted: Optional[str] = None              # record_id of a just-emitted record
    skipped_reason: Optional[str] = None       # e.g. "warehouse_disabled"
    output_file: Optional[str] = None
    audit_event_id: Optional[str] = None
