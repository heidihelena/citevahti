"""Claim citation-integrity report (the 4-state "unit-test results").

The manuscript is treated like code: each claim is a test case whose state is
DERIVED from its candidates, blinded ratings, and final decisions. The four
states (ADR-0002, reconciled): three evidence-fit states + one terminal.

  [oo] accepted          — has accepted, supporting evidence (was "verified"
                           before v0.16; renamed because the tool checks
                           citation support, not truth — finding #7-B)
  [o ] needs_support     — no citation / no accepted supporting evidence yet
  [r ] review_needed     — unresolved discordance or a 2nd-review decision
  [d ] decision_recorded — every candidate settled, none accepted (terminal)
  [u ] untestable        — the cited source is outside the indexed-literature
                           scope (book/chapter/grey lit); marked by the human,
                           NOT a failure state and never "needs attention"

Read-only: it computes no new judgments and mutates nothing.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .claim_support import FitScores

CLAIM_STATES = ("accepted", "needs_support", "review_needed", "decision_recorded",
                "untestable")
STATE_CODE = {"accepted": "oo", "needs_support": "o ",
              "review_needed": "r ", "decision_recorded": "d ",
              "untestable": "u "}
# Plain-language pairing for the [oo]/[o]/[r]/[d]/[u] codes — the manuscript's test
# results, in words. Stable (asserted by tests); used in reports, docs, and UI copy.
STATE_LABEL = {"accepted": "accepted", "needs_support": "needs support",
               "review_needed": "review needed", "decision_recorded": "decided",
               "untestable": "untestable"}


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
    retracted: Optional[bool] = None          # True = flagged by the retraction scan;
                                              # None = not flagged (which includes "not checked")
    stale: bool = False                       # True = the rating/decision was formed against an
                                              # older claim wording (claim revised since) — re-check


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
    untestable_reason: Optional[str] = None         # why the source is out of indexed scope
    has_stale_bonds: bool = False                   # any evidence formed against an older wording
    inconsistent: bool = False                      # a decision disagrees with its rating (edited outside CiteVahti)
    inconsistency: Optional[str] = None             # the first inconsistency message, if any


class ReportProvenance(BaseModel):
    """What this report can and cannot vouch for, embedded in the artifact itself.

    The audit chain is tamper-evident (hash-chained), NOT cryptographically
    signed: it shows the recorded order of work against an honest ledger, but a
    wholesale regenerated ledger would also validate. Report readers must see
    that limitation in the report, not in a developer doc.
    """
    model_config = ConfigDict(extra="forbid")
    audit_head_hash: Optional[str] = None       # hash of the last audit entry at generation
    audit_entries: Optional[int] = None         # chain length at generation
    audit_chain_intact: Optional[bool] = None   # AuditLog.verify() at generation
    ledger_claims_total: Optional[int] = None   # all claims in the ledger (report may cover a subset)
    last_retraction_scan_at: Optional[str] = None  # audit ts of the most recent scan, if any
    retraction_source: Optional[str] = None     # how retractions are checked + the blind spot


class ClaimReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generated_at: str
    total: int = 0
    counts: dict = Field(default_factory=dict)   # state -> count
    rows: list[ClaimReportRow] = Field(default_factory=list)
    provenance: Optional[ReportProvenance] = None
    # ledger-integrity warnings (e.g. a decision edited outside CiteVahti). Non-empty
    # means at least one claim's state can't be trusted until the ledger is repaired.
    warnings: list[str] = Field(default_factory=list)


class ParagraphSentence(BaseModel):
    """One sentence of a pasted paragraph, matched (or not) to a tracked claim."""

    model_config = ConfigDict(extra="forbid")
    text: str
    status: str                              # reviewed | attention | new
    claim_id: Optional[str] = None           # the matched ledger claim, if any
    state: Optional[str] = None              # its report state when matched
    reason: Optional[str] = None             # why it needs attention (status == attention)
    action: Optional[str] = None             # the next step (status == attention)


class ParagraphCheck(BaseModel):
    """Check-a-paragraph result: per-sentence status + a quick tally, for the
    everyday in-the-writing loop (what have I vetted, what needs me, what's new)."""

    model_config = ConfigDict(extra="forbid")
    total: int = 0                           # claim-like sentences considered
    reviewed: int = 0                        # matched a vetted claim, nothing to do
    attention: int = 0                       # matched a claim that needs attention
    new: int = 0                             # not tracked yet (new, or not a claim)
    sentences: list[ParagraphSentence] = Field(default_factory=list)
