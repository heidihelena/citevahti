"""Assistive extraction result schemas (candidates only -- never confirmed)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import Provenance
from .passage import RetrievedPassage

EXTRACT_FIELDS = [
    "design", "population", "intervention", "comparator", "outcome",
    "sample_size", "effect_estimate", "follow_up", "setting",
]


class FieldCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    value: str
    passage: RetrievedPassage
    score: Optional[float] = None


class ExtractResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "degraded"] = "ok"
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    subject: dict = Field(default_factory=dict)   # echo of the ItemRef
    fields: list[str] = Field(default_factory=list)
    candidates_by_field: dict[str, list[FieldCandidate]] = Field(default_factory=dict)
    unverifiable_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
