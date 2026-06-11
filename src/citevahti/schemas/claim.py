"""Operational claim schema (ADR-0001, step 1): the claim is the spine.

A claim is a first-class, manuscript-anchored assertion that *candidate papers*
will later be tested against. It is NOT evidence, NOT a decision, and NOT a
citation -- those come downstream (candidates -> claim-support ratings ->
final decision -> guarded write). Creating a claim mutates nothing in Zotero
and decides nothing; it only records *what is being asserted, where, and who/what
extracted it*.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION
from .common import Provenance

# Controlled claim types (manifesto). 'other' is the honest escape hatch -- we
# never silently coerce an unclear claim into a clinical category.
CLAIM_TYPES = (
    "effectiveness",
    "diagnostic_accuracy",
    "prognosis",
    "risk_factor",
    "mechanism",
    "background",
    "guideline_recommendation",
    "implementation",
    "other",
)

EXTRACTED_BY = ("human", "ai", "imported")


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    claim_id: str
    project_id: Optional[str] = None        # reserved for the hosted operational DB
    manuscript_id: Optional[str] = None
    claim_text: str
    claim_type: Literal[CLAIM_TYPES] = "other"  # type: ignore[valid-type]
    manuscript_location: Optional[str] = None   # e.g. "Discussion ¶3" or "file:char:1200-1280"
    extracted_by: Literal[EXTRACTED_BY] = "human"  # type: ignore[valid-type]
    extraction_model: Optional[str] = None       # required when extracted_by == "ai"
    created_at: Optional[str] = None
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None
    # A pending rewrite the human can review as a diff and accept/reject. The agent
    # may *propose* (by == "ai", model required); only a human *accepts* (never silent).
    proposed_revision: Optional[str] = None
    proposed_revision_by: Optional[Literal[EXTRACTED_BY]] = None  # type: ignore[valid-type]
    proposed_revision_model: Optional[str] = None
    # Out-of-indexed-scope marker: the cited source cannot be auto-checked against
    # the indexed literature (book, chapter, grey literature, non-indexed source).
    # Set by the human with a reason; the report then shows the claim as
    # "untestable" instead of letting it look like a failure ("needs support").
    untestable_reason: Optional[str] = None
