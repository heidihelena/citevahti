"""map_bootstrap report schema (minimal deterministic seeding)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import Provenance


class ProposedNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str
    type: str
    label: Optional[str] = None
    citekey: Optional[str] = None


class ProposedLink(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: str = Field(alias="from")
    to: str
    type: str


class MapBootstrapReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    guideline_path: str
    dry_run: bool = True
    written: bool = False
    sections: list[str] = Field(default_factory=list)
    resolved_citekeys: list[str] = Field(default_factory=list)
    orphan_citekeys: list[str] = Field(default_factory=list)   # unresolved; never invented
    outcomes: list[str] = Field(default_factory=list)
    proposed_nodes: list[ProposedNode] = Field(default_factory=list)
    proposed_links: list[ProposedLink] = Field(default_factory=list)
    status: str = "ok"
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None
