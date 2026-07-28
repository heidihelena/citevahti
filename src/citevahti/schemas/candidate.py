"""Claim ↔ paper candidates (ADR-0001, step 2).

A *candidate* records that a specific paper entered consideration **for a
specific claim**, and *why* (which query, which source, what rank). It is the
hinge between the claim (the spine) and the downstream claim-support rating and
final decision. A candidate is NOT a decision and NOT a citation: linking a
candidate mutates no Zotero state and asserts no support.

Candidates for a claim are grouped in one ``candidates/<claim_id>.json`` file so
that "the candidates for this claim" is a single, dedupe-able, audited object.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION
from .common import Provenance


class ClaimPaperCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    claim_id: str
    # provenance of how it was found
    record_id: Optional[str] = None          # the intake hit it came from
    intake_batch_id: Optional[str] = None
    retrieval_query: Optional[str] = None     # the exact query (never rewritten)
    retrieval_source: Optional[str] = None    # "pubmed" | "manual" | ...
    retrieval_rank: Optional[int] = None      # position in the result list
    why_found: Optional[str] = None           # e.g. dedupe status / note
    already_in_zotero: Optional[bool] = None
    dedupe_status: Optional[str] = None
    retracted: Optional[bool] = None          # set by the retraction scan (OpenAlex is_retracted)
    # reuse rights — set by the licence scan (OpenAlex open_access). REPORTS, never DECIDES:
    # these describe the source's licensing so a human/tool can judge reuse; CiteVahti
    # never says "you may republish". None = unknown (not scanned, or not found).
    oa_status: Optional[str] = None           # gold | green | hybrid | bronze | closed | None
    license: Optional[str] = None             # e.g. "cc-by", "cc-by-nc-nd"; None = unknown/closed
    # paper metadata snapshot (canonical papers table comes later)
    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: Optional[str] = None
    journal: Optional[str] = None
    year: Optional[int] = None
    publication_date: Optional[str] = None
    abstract: Optional[str] = None            # the paper's own abstract (blinding-safe;
    #                                           NOT an AI assessment) — read before rating
    created_at: Optional[str] = None


class ClaimCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    claim_id: str
    candidates: list[ClaimPaperCandidate] = Field(default_factory=list)
    updated_at: Optional[str] = None
    provenance: Optional[Provenance] = None
    audit_event_id: Optional[str] = None


class CandidateMetadataDivergence(BaseModel):
    """One field where a linked candidate and a re-imported record disagree.

    Reported, never applied: dedupe matches on identifier, so a corrected record links to
    the candidate already on file and its stale metadata stands. Refreshing it silently
    would rewrite what a rater saw, so the divergence is surfaced and the correction is an
    explicit, audited act (``CandidateService.refresh_from_intake``).
    """

    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    record_id: Optional[str] = None
    field: str
    current: Optional[str] = None      # what the candidate holds (None = the batch fills a gap)
    incoming: Optional[str] = None     # what the re-imported record says


class CandidateLinkReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    intake_batch_id: str
    linked: int = 0
    skipped_duplicates: int = 0
    total_candidates: int = 0
    # Fields where a matched candidate disagrees with the incoming record. Nothing was
    # changed on the strength of these -- they say a repair may be warranted.
    divergences: list[CandidateMetadataDivergence] = Field(default_factory=list)
    # The candidates this link request is ABOUT: for every intake hit considered, the
    # candidate that now represents it — freshly linked or already present. Named and
    # shaped like ``ClaimCandidates.candidates`` so one reader handles both results, and
    # reported for matches too so a re-run answers "which candidates are these sources?"
    # rather than an unhelpful `linked: 0`.
    candidates: list[ClaimPaperCandidate] = Field(default_factory=list)
    audit_event_id: Optional[str] = None


class CandidateRepairReport(BaseModel):
    """The result of an explicit metadata correction: what changed, and what had already
    been judged against the old values."""

    model_config = ConfigDict(extra="forbid")
    claim_id: str
    candidate_id: str
    intake_batch_id: str
    corrected: list[CandidateMetadataDivergence] = Field(default_factory=list)
    # Support ratings for this pair that already carry a human judgement. A correction is
    # still the right thing to do -- but the judgement was made against what the record
    # used to say, so it is named here and in the audit payload, never quietly absorbed.
    human_rated_before: int = 0
    audit_event_id: Optional[str] = None
