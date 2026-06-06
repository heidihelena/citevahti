"""PRISMA ledger schema (human decisions only; AI votes referenced by rating_id)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION
from .common import Provenance

PRISMA_STAGES = ("title_abstract", "full_text")
PRISMA_DECISIONS = ("include", "exclude", "maybe", "not_retrieved")
PRISMA_DECIDERS = ("human", "panel")


class PrismaDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str
    stage: str
    decision: str
    reason: Optional[str] = None        # required when excluded (validator-enforced)
    decider: str                        # human | panel only
    decided_at: str
    notes: Optional[str] = None


class PrismaLedgerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    question_id: str
    created_at: str
    updated_at: str
    decisions: list[PrismaDecision] = Field(default_factory=list)
    counts: dict = Field(default_factory=dict)
    excluded_reasons: dict = Field(default_factory=dict)
    ai_vote_refs: list[str] = Field(default_factory=list)   # rating_ids only, never decisions
    generated_files: list[str] = Field(default_factory=list)
    status: str = "ok"
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None
