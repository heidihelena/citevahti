"""Deterministically retrieved passages and the retrieval result envelope."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import Provenance

RetrievalMethod = Literal["fulltext", "annotation"]


class RetrievedPassage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    citekey: Optional[str] = None
    zotero_key: str
    attachment_key: Optional[str] = None
    page: Optional[str] = None          # null when unknown -- never fabricated
    location: Optional[str] = None      # e.g. "char:1200-1320" or "pageIndex:3"
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    quote: str
    text_hash: str
    retrieval_method: RetrievalMethod
    section: Optional[str] = None        # e.g. "Results" — where in the paper the passage sits
    score: Optional[float] = None
    provenance: Provenance


class PassageRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "degraded"] = "ok"
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    citekey: Optional[str] = None
    zotero_key: Optional[str] = None
    passages: list[RetrievedPassage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
