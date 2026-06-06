"""Guarded write-back schemas (step 9).

A write is previewed (dry-run, default) producing a WriteDiff + confirmation
token, then applied with the token producing a WriteResult. Nothing is written
to Zotero on dry-run; confirmed writes append an audit event. No silent fallback.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import Provenance


class WriteOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str                              # note_add | tag_add | ... | tag_mirror | intake_push
    library: str = "personal"
    targets: list[str] = Field(default_factory=list)   # zotero item keys / citekeys
    payload: dict = Field(default_factory=dict)
    proposed_changes: list[str] = Field(default_factory=list)
    structured: dict = Field(default_factory=dict)     # added/removed/created/skipped


class WriteDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    library: str
    targets: list[str] = Field(default_factory=list)
    proposed_changes: list[str] = Field(default_factory=list)
    structured: dict = Field(default_factory=dict)
    confirm_token: str
    dry_run: bool = True
    backend_kind: str = "unavailable"
    backend_available: bool = False
    backend_supports_kind: bool = True    # does the configured backend support this op kind?
    status: str = "preview"                # preview | not_mirrorable | unsupported
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None


class WriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    library: str
    targets: list[str] = Field(default_factory=list)
    applied: bool = False
    status: str = "applied"                # applied | unavailable | failed
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    result: dict = Field(default_factory=dict)
    backend_kind: str = "unavailable"
    audit_event_id: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
