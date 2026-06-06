"""Candidate validators (ADR-0001, step 2)."""

from __future__ import annotations

from ..schemas.candidate import ClaimCandidates
from .errors import ValidationError


class CandidateError(ValidationError):
    code = "candidate_invalid"


def validate_claim_candidates(cc: ClaimCandidates, *, require_audit: bool = False) -> None:
    if not cc.claim_id:
        raise CandidateError("claim candidates set must reference a claim_id")
    if cc.provenance is None:
        raise CandidateError("claim candidates set is missing provenance")
    seen: set[str] = set()
    for c in cc.candidates:
        if c.claim_id != cc.claim_id:
            raise CandidateError(
                f"candidate {c.candidate_id!r} claim_id {c.claim_id!r} != set {cc.claim_id!r}")
        if c.candidate_id in seen:
            raise CandidateError(f"duplicate candidate_id {c.candidate_id!r} within the claim")
        seen.add(c.candidate_id)
        # a candidate must identify its paper somehow (never an empty link)
        if not (c.pmid or c.doi or c.title):
            raise CandidateError(f"candidate {c.candidate_id!r} has no pmid/doi/title")
    if require_audit and not cc.audit_event_id:
        raise CandidateError("claim candidates set is missing audit_event_id after write")
