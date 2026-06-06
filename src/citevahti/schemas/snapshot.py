"""Snapshot schema: a hashed, read-only capture of corpus + evidence-map state."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION
from .common import Provenance


class ProbeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available: bool = False
    version: Optional[str] = None
    version_status: Optional[str] = None
    detail: Optional[str] = None


class SnapshotItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    zotero_key: str
    citekey: Optional[str] = None        # never invented
    item_version: Optional[int] = None
    title: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    year: Optional[int] = None
    metadata_hash: str
    fulltext_hash: Optional[str] = None
    attachment_hashes: Optional[list[str]] = None
    retraction_status: str = "unknown"


class SnapshotRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    snapshot_id: str
    label: Optional[str] = None
    created_at: str
    library: str
    zotero_probe: ProbeSummary = Field(default_factory=ProbeSummary)
    bbt_probe: ProbeSummary = Field(default_factory=ProbeSummary)
    citekey_coverage: Literal["ok", "degraded"] = "ok"
    include_fulltext_hashes: bool = False
    items: dict[str, SnapshotItem] = Field(default_factory=dict)  # keyed by citekey or item key
    evidence_map_hash: Optional[str] = None
    reverse_index_hash: Optional[str] = None

    status: Literal["ok", "degraded"] = "ok"
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None
