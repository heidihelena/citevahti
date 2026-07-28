"""Bulk claim import: what one JSONL corpus load did (ADR-0001 steps 1-3, in one command).

The report is the whole point of the command. A loader that fans a file out into claims,
candidates and open rating slots must say *exactly* what it touched — per row, per source —
so a run can be checked, resumed, or handed to someone else. It records no judgement: the
import opens rating slots and stops there.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION


class ImportedSource(BaseModel):
    """One (claim, source) pair after import."""

    model_config = ConfigDict(extra="forbid")
    record_id: str
    identifier: Optional[str] = None     # "doi:…" / "pmid:…"; None when only a title was given
    title: Optional[str] = None
    candidate_id: Optional[str] = None   # None on a dry run — the claim does not exist yet
    rating_id: Optional[str] = None      # the OPEN support slot; never a judgement
    status: Literal["linked", "already_linked", "would_link"] = "linked"


class ImportedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row: int                             # 1-based line number in the source file
    claim_id: Optional[str] = None       # None on a dry run for a claim that would be created
    claim_text: str
    status: Literal["created", "matched", "would_create"] = "created"
    sources: list[ImportedSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ClaimsImportReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    dry_run: bool = False
    intake_batch_id: Optional[str] = None    # None on a dry run: nothing was staged
    rows: int = 0
    claims_created: int = 0
    claims_matched: int = 0                  # already in the ledger — a re-run, not a duplicate
    candidates_linked: int = 0
    candidates_already_linked: int = 0
    ratings_opened: int = 0
    title_only_sources: int = 0              # cannot be deduped by identifier (invariant 11)
    claims: list[ImportedClaim] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
