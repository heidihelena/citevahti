"""Claim citation-integrity report (the 4-state "unit-test results").

The manuscript is treated like code: each claim is a test case whose state is
DERIVED from its candidates, blinded ratings, and final decisions. The four
states (ADR-0002, reconciled): three evidence-fit states + one terminal.

  [oo] verified          — has accepted, supporting evidence
  [o ] needs_support     — no citation / no accepted supporting evidence yet
  [r ] review_needed     — unresolved discordance or a 2nd-review decision
  [d ] decision_recorded — every candidate settled, none accepted (terminal)

Read-only: it computes no new judgments and mutates nothing.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .claim_support import FitScores

CLAIM_STATES = ("verified", "needs_support", "review_needed", "decision_recorded")
STATE_CODE = {"verified": "oo", "needs_support": "o ",
              "review_needed": "r ", "decision_recorded": "d "}
# Plain-language pairing for the [oo]/[o]/[r]/[d] codes — the manuscript's test
# results, in words. Stable (asserted by tests); used in reports, docs, and UI copy.
STATE_LABEL = {"verified": "verified", "needs_support": "needs support",
               "review_needed": "review needed", "decision_recorded": "decided"}


class ClaimEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    decision_id: Optional[str] = None        # the final decision for this pair, if any
    rating_id: Optional[str] = None          # the (claim, candidate) support rating, if any
    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: Optional[str] = None
    support_status: Optional[str] = None      # final/human support value for the pair
    human_support: Optional[str] = None       # the human's blinded rating (None until committed)
    ai_support: Optional[str] = None          # AI value, or "hidden" while the human hasn't rated
    final_decision: Optional[str] = None
    agreement: Optional[str] = None
    # The human/decided view of the evidence (never the blinded AI's), so the card
    # can show PICO fit + an excerpt without leaking the AI assessment. All None
    # until the human commits a rating — mirrors `ai_support`'s blinding.
    fit: Optional[FitScores] = None           # human PICO + claim fit subscores
    fit_total: Optional[int] = None           # sum of fit subscores, 0..8
    excerpt: Optional[str] = None             # verbatim quote from the human's source passage


class ClaimReportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    claim_text: str
    claim_type: Optional[str] = None
    manuscript_location: Optional[str] = None
    state: Literal[CLAIM_STATES]             # type: ignore[valid-type]
    code: str                                 # oo / o / r / d
    candidate_count: int = 0
    accepted_count: int = 0
    evidence: list[ClaimEvidence] = Field(default_factory=list)
    proposed_revision: Optional[str] = None        # pending rewrite, shown as a diff
    proposed_revision_by: Optional[str] = None      # "ai" | "human" | "imported"


class ClaimReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generated_at: str
    total: int = 0
    counts: dict = Field(default_factory=dict)   # state -> count
    rows: list[ClaimReportRow] = Field(default_factory=list)
