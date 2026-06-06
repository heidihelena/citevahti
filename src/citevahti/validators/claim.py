"""Claim validators (ADR-0001, step 1)."""

from __future__ import annotations

from ..schemas.claim import CLAIM_TYPES, EXTRACTED_BY, Claim
from .errors import ValidationError


class ClaimError(ValidationError):
    code = "claim_invalid"


def validate_claim(claim: Claim, *, require_audit: bool = False) -> None:
    if not (claim.claim_text or "").strip():
        raise ClaimError("claim_text must be non-empty")
    if claim.claim_type not in CLAIM_TYPES:
        raise ClaimError(f"unsupported claim_type {claim.claim_type!r}")
    if claim.extracted_by not in EXTRACTED_BY:
        raise ClaimError(f"unsupported extracted_by {claim.extracted_by!r}")
    # Mirror the AI-needs-provenance discipline: an AI-extracted claim must name
    # the model that produced it (so the ledger never has anonymous AI output).
    if claim.extracted_by == "ai" and not (claim.extraction_model or "").strip():
        raise ClaimError("an AI-extracted claim must record extraction_model")
    if claim.provenance is None:
        raise ClaimError("claim is missing provenance")
    if require_audit and not claim.audit_event_id:
        raise ClaimError("claim is missing audit_event_id after write")
