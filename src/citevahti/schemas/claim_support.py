"""Claim-support rating (ADR-0001, step 3) — the core asset dimension.

This answers the question study-quality schemes (GRADE/RoB2) do NOT: *does this
paper support THIS claim, and how well does it fit?* It rides on the same dual-
rating invariants as the study-quality engine and **reuses** its value blocks
(`AIProvenance`, `Comparison`, `Adjudication`, `Blinding`) verbatim, but is keyed
to a ``(claim_id, candidate_id)`` pair and carries PICO fit subscores.

Invariants (mirrored, enforced in validators + engine + store):
  - the human value is locked after commit and never overwritten;
  - the AI rating is blind + advisory and can NEVER become final automatically;
  - a discordance is resolved only by human/panel adjudication;
  - ``final_value`` is never sourced from the AI value.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION
from .common import PassageRef
from .rating import AIProvenance, Adjudication, Blinding, Comparison

# The controlled support vocabulary (manifesto). 'unclear' is an honest value, not
# an abstain: a human may decide the support is genuinely unclear.
SUPPORT_VALUES = (
    "directly_supports",
    "partially_supports",
    "indirectly_supports",
    "overstated",        # cited paper supports a *weaker* claim than the one made (overclaim)
    "does_not_support",
    "contradicts",
    "unclear",
)

# Plain-language definitions of each support value — the single source the AI prompt
# (and any human-facing copy) should use, so the controlled vocabulary is applied the
# same way everywhere.
SUPPORT_DEFINITIONS = {
    "directly_supports": "the paper's findings directly support this exact claim",
    "partially_supports": "the paper supports part of the claim but not all of it",
    "indirectly_supports": "the paper supports the claim only indirectly (related population, surrogate outcome, or inference)",
    "overstated": "the paper supports a WEAKER version of the claim — the claim overstates the evidence (broader population, stronger effect, or an extra outcome)",
    "does_not_support": "the paper is on-topic but does not actually support this claim",
    "contradicts": "the paper's findings argue against this claim",
    "unclear": "the available text genuinely does not let you decide",
}

# PICO + claim fit, each 0 (poor) / 1 (partial) / 2 (good).
FIT_FIELDS = ("population_fit", "intervention_fit", "outcome_fit", "claim_fit")


class FitScores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    population_fit: Optional[int] = None
    intervention_fit: Optional[int] = None
    outcome_fit: Optional[int] = None
    claim_fit: Optional[int] = None


class SupportHumanRating(BaseModel):
    """Locked after commit; never overwritten (enforced at the store)."""

    model_config = ConfigDict(extra="forbid")
    value: Optional[Literal[SUPPORT_VALUES]] = None  # type: ignore[valid-type]
    fit: FitScores = Field(default_factory=FitScores)
    committed_at: str
    committed_by: str
    rationale: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    source_passages: list[PassageRef] = Field(default_factory=list)
    locked: bool = True


class SupportAIRating(BaseModel):
    """Blind, independent advisory rating. Can NEVER become final automatically."""

    model_config = ConfigDict(extra="forbid")
    value: Optional[Literal[SUPPORT_VALUES]] = None  # type: ignore[valid-type]  # None when abstained
    abstained: bool = False
    confidence: Optional[float] = None
    fit: FitScores = Field(default_factory=FitScores)
    supporting_passages: list[PassageRef] = Field(default_factory=list)
    domain_reasoning: Optional[str] = None
    task_type: Optional[str] = None
    provenance: AIProvenance


class ClaimSupportRating(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    rating_id: str
    rating_set_id: Optional[str] = None       # links multiple human raters
    claim_id: str
    candidate_id: str
    human_rating: Optional[SupportHumanRating] = None
    ai_rating: Optional[SupportAIRating] = None
    comparison: Comparison = Field(default_factory=Comparison)
    adjudication: Adjudication = Field(default_factory=Adjudication)
    blinding: Blinding = Field(default_factory=Blinding)
    # The claim_text_hash this rating was formed against, stamped once at first
    # write. When the claim is later revised, current hash != this → the bond is
    # stale (the rating predates the wording). Optional/legacy-safe: a record
    # without it reads as 'unknown', never silently 'current'. See claims/bonds.py.
    claim_text_hash: Optional[str] = None
    audit_event_id: Optional[str] = None
