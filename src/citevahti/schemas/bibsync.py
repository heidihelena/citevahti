"""The structured report returned by `bib_sync`."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import Provenance

BibSyncStatus = Literal["ok", "degraded", "failed"]
ExportFormat = Literal["bibtex", "biblatex", "csl-json"]


class FileCitations(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    citekeys: list[str] = Field(default_factory=list)  # per-file, first-seen order


class BibSyncReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: BibSyncStatus = "ok"
    error_code: Optional[str] = None
    remediation: Optional[str] = None

    scanned_files: list[str] = Field(default_factory=list)
    citations_per_file: list[FileCitations] = Field(default_factory=list)
    unique_citekeys: list[str] = Field(default_factory=list)  # global first-seen order
    resolved_citekeys: list[str] = Field(default_factory=list)
    orphan_citekeys: list[str] = Field(default_factory=list)   # cited but unresolved
    bibliography_files: list[str] = Field(default_factory=list)  # existing local .bib found
    unused_citekeys: list[str] = Field(default_factory=list)   # in .bib but not cited

    generated_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_event_id: Optional[str] = None
    provenance: Optional[Provenance] = None
