"""The evidence map: typed nodes, links, attachments + a citekey-centered
reverse index (Patch 6).

Attachments are the typed provenance objects hung off the corpus -- extracted
fields, verified claims, assessments, staleness/retraction flags, screening
decisions. The reverse index is keyed by citekey so a single lookup answers
"everything we know about this source".
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import ItemRef, PassageRef, Provenance

SchemeKind = Literal["GRADE", "RoB2", "ROBINS-I", "Generic"]

NodeType = Literal[
    "item",
    "claim",
    "passage",
    "rating",
    "recommendation",
    "section",
    "outcome",
    "study",
]

AttachmentKind = Literal[
    "extracted_field",
    "verified_claim",
    "assessment",
    "staleness_flag",
    "retraction_flag",
    "screening_decision",
]

LinkType = Literal[
    "cites",
    "supports",
    "rated_by",
    "about_outcome",
    "derived_from",
    "recommends",
    "in_section",
]


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str
    type: NodeType
    item: Optional[ItemRef] = None
    passage: Optional[PassageRef] = None
    label: Optional[str] = None


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    # ``from`` is a Python keyword; expose it as ``from_`` with the JSON alias.
    from_: str = Field(alias="from")
    to: str
    type: LinkType
    link_id: Optional[str] = None  # assigned on add so the reverse index can cite it


class Attachment(BaseModel):
    """A typed provenance object hung off the corpus.

    The optional scope fields operationalize the per-kind scope rules without
    replacing the schema: ``study_node_id`` / ``outcome_node_id`` express an
    assessment's scope, ``scheme_kind`` distinguishes GRADE (outcome-level) from
    RoB (study or study x outcome), ``rating_id`` links a rating record, and
    ``provenance`` is required for extracted fields.
    """

    model_config = ConfigDict(extra="forbid")
    attachment_id: str
    kind: AttachmentKind
    item: Optional[ItemRef] = None
    target_node_id: Optional[str] = None
    passage: Optional[PassageRef] = None
    payload: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    # operational scope / provenance fields (all optional, kind-dependent)
    citekey: Optional[str] = None
    study_node_id: Optional[str] = None
    outcome_node_id: Optional[str] = None
    scheme_kind: Optional[SchemeKind] = None
    rating_id: Optional[str] = None
    claim_id: Optional[str] = None
    claim_text: Optional[str] = None
    decision: Optional[str] = None
    decided_by: Optional[str] = None
    provenance: Optional[Provenance] = None


class ReverseIndexEntry(BaseModel):
    """Citekey-centered roll-up of everything attached to one source."""

    model_config = ConfigDict(extra="forbid")
    study_node_id: Optional[str] = None
    attachment_ids: list[str] = Field(default_factory=list)
    link_ids: list[str] = Field(default_factory=list)
    rating_ids: list[str] = Field(default_factory=list)
    recommendation_node_ids: list[str] = Field(default_factory=list)
    outcome_node_ids: list[str] = Field(default_factory=list)
    stale_flags: list[str] = Field(default_factory=list)


class EvidenceMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: list[Node] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    reverse_index: dict[str, ReverseIndexEntry] = Field(default_factory=dict)
