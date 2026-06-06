"""Claim-check result schemas.

``claim_check`` never asserts truth. The only positive status is
``supported_candidate`` -- the ``_candidate`` qualifier is mandatory.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import Provenance
from .passage import RetrievedPassage

ClaimStatus = Literal["supported_candidate", "no_support_found", "unverifiable"]


class PerCitekeyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    citekey: str
    status: ClaimStatus
    zotero_key: Optional[str] = None
    reason: Optional[str] = None
    score: Optional[float] = None
    passages: list[RetrievedPassage] = Field(default_factory=list)


class ClaimCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_text: str
    aggregate_status: ClaimStatus
    require_page: bool = False
    per_citekey: list[PerCitekeyResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
