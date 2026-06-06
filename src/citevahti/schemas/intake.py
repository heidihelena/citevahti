"""Operational intake schema: pre-decision candidate records (step 5).

Intake files stage PubMed/manual search results. They are NOT inclusion
decisions and never enter Zotero or the evidence map in this step. Every hit's
``decision`` is null.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION
from .common import Provenance

PROVIDERS = ("pubmed", "manual")
DEDUPE_STATUSES = ("new", "already_in_library", "already_in_prior_intake", "duplicate_in_run")


class IntakeHit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: str
    authors: list[str] = Field(default_factory=list)
    journal: Optional[str] = None
    publication_date: Optional[str] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
    dedupe_status: str = "new"
    decision: Optional[str] = None   # MUST stay null in step 5 (enforced by validator)
    candidate_recommendation_node_ids: list[str] = Field(default_factory=list)
    candidate_outcome_node_ids: list[str] = Field(default_factory=list)


class IntakeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    batch_id: str
    provider: str                     # "pubmed" | "manual"
    question_id: Optional[str] = None

    # PubMed: query/exact_query; manual: source_label
    query: Optional[str] = None
    exact_query: Optional[str] = None
    source_label: Optional[str] = None
    source_format: Optional[str] = None       # manual: ris|csv|bibtex
    source_hash: Optional[str] = None         # manual: file/text hash

    run_at: Optional[str] = None              # PubMed
    imported_at: Optional[str] = None         # manual
    last_run_at: Optional[str] = None         # null for literature_search (step 5)

    # surveillance_refresh provenance (step 6)
    original_query_id: Optional[str] = None
    exact_query_sent: Optional[str] = None    # original query + mechanical date append
    baseline_date: Optional[str] = None       # from the saved query's own run_at

    # environment / provenance of the run
    ncbi_email_present: Optional[bool] = None
    ncbi_api_key_present: Optional[bool] = None
    rate_tier: Optional[str] = None           # "3rps" | "10rps"
    result_count: Optional[int] = None        # records RETURNED (staged, <= max_results)
    total_count: Optional[int] = None         # records MATCHED in PubMed (the true total)
    query_translation: Optional[str] = None   # how NCBI parsed the query (methods log)
    dedupe_against: list[str] = Field(default_factory=list)
    library_dedupe_status: Optional[str] = None   # "ok" | "degraded"
    seen_set_digest: Optional[str] = None

    # honest degradation
    status: Literal["ok", "degraded"] = "ok"
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    # True when PubMed reported warnings / a query translation that changed intent:
    # the staged results may not match what the user meant -> a human should check.
    review_required: bool = False

    hits: list[IntakeHit] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None


# Conceptual aliases used by the tool surface.
PubMedIntakeRecord = IntakeRecord
ManualImportRecord = IntakeRecord
