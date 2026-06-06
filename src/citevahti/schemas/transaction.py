"""Zotero write transaction (ADR-0001 step 5) — preview/commit/undo with a snapshot.

Promotes the one-use write token into a durable, auditable object so every write
has a status, an undo path, and (for a validated write) a link back to the claim,
candidate, and final decision it rests on. This is the object that makes the §6
invariant enforceable: no validated Zotero write exists without one.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION
from .common import Provenance

TRANSACTION_STATUS = ("previewed", "committed", "undone", "failed")


class ZoteroTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    transaction_id: str
    kind: str                                  # the write op kind (e.g. "item_add")
    validated: bool = False                    # True = decision-gated; False = labelled staging
    status: Literal[TRANSACTION_STATUS] = "previewed"  # type: ignore[valid-type]
    library: str = "personal"
    collection_key: Optional[str] = None
    # the validated-write chain (§6): set for validated writes
    claim_id: Optional[str] = None
    candidate_id: Optional[str] = None
    decision_id: Optional[str] = None
    proposed_changes: list[str] = Field(default_factory=list)
    result: dict = Field(default_factory=dict)          # backend result (created_keys, ...)
    undo_snapshot: dict = Field(default_factory=dict)   # what an undo reverses
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    provenance: Optional[Provenance] = None
    created_at: Optional[str] = None
    committed_at: Optional[str] = None
    undone_at: Optional[str] = None
    audit_event_id: Optional[str] = None
