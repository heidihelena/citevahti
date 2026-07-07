"""Claim and candidate ledger operations (ADR-0010 PR 1e — first ledger-write group).

Recording and revising manuscript claims, and linking/unlinking their candidate papers.
Unlike the read-only groups these DO write — but only to the local, audited CiteVahti
ledger, never to a Zotero library and never the final decision. Every mutation is
recorded on the tamper-evident audit trail; revisions apply nothing until the human
accepts them; unlinking is non-destructive (the claim and audit trail are kept).

This is NOT the write-privileged Zotero surface — the key/OAuth connect functions and the
guarded library writes stay in the facade for ``tools/writeback.py`` (ADR-0010 §3/§5,
reviewed hardest, moved last).

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ._common import _open_store


def add_claim(claim_text: str, claim_type: str = "other", *,
              manuscript_location: Optional[str] = None, manuscript_id: Optional[str] = None,
              project_id: Optional[str] = None, extracted_by: str = "human",
              extraction_model: Optional[str] = None, root: Optional[str] = None):
    """Record a first-class manuscript claim. Mutates no Zotero state, decides nothing."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).add_claim(
        claim_text, claim_type, manuscript_location=manuscript_location,
        manuscript_id=manuscript_id, project_id=project_id, extracted_by=extracted_by,
        extraction_model=extraction_model)


def list_claims(*, root: Optional[str] = None):
    """List recorded claims (read-only)."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).list_claims()


def claim_mark_untestable(claim_id: str, reason: Optional[str], *,
                          root: Optional[str] = None):
    """Mark a claim's cited source as outside the indexed-literature scope
    (book/chapter/grey literature), or clear the marker with ``reason=None``.
    The report then shows ``[u] untestable`` instead of ``needs_support``."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).mark_untestable(claim_id, reason)


def propose_revision(claim_id: str, new_text: str, *, extracted_by: str = "human",
                     extraction_model: Optional[str] = None, root: Optional[str] = None):
    """Attach a pending rewrite to a claim. Applies nothing; the human reviews the diff."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).propose_revision(
        claim_id, new_text, extracted_by=extracted_by, extraction_model=extraction_model)


def accept_revision(claim_id: str, *, expected_text: Optional[str] = None,
                    root: Optional[str] = None):
    """Apply a pending rewrite to the claim text (human action; audited before/after)."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).accept_revision(
        claim_id, expected_text=expected_text)


def reject_revision(claim_id: str, *, root: Optional[str] = None):
    """Discard a pending rewrite; the claim text is unchanged (audited)."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).reject_revision(claim_id)


def claim_bond_status(claim_id: str, *, root: Optional[str] = None):
    """Report whether a claim's evidence assessments are stale after a revision.

    Returns the bond freshness for the claim — which claim-support ratings /
    decisions were formed against an older wording (``stale``) and so should be
    re-checked. Advisory only; nothing is invalidated."""
    from ..claims.bonds import claim_bond_status as _status
    return _status(_open_store(root), claim_id)


def link_candidates(claim_id: str, intake_batch_id: str, record_ids: Optional[list] = None, *,
                    root: Optional[str] = None):
    """Link staged intake hits to a claim as candidates (ADR-0001 step 2). No Zotero write."""
    from ..claims import CandidateService
    return CandidateService(_open_store(root)).link_from_intake(
        claim_id, intake_batch_id, record_ids=record_ids)


def list_candidates(claim_id: str, *, root: Optional[str] = None):
    """List a claim's candidate papers (read-only)."""
    from ..claims import CandidateService
    return CandidateService(_open_store(root)).list_for_claim(claim_id)


def unlink_candidate(claim_id: str, candidate_id: str, *, root: Optional[str] = None):
    """Unlink one candidate paper from a claim (the 'wrong paper' case). The
    removal is audited and non-destructive — the claim and the audit trail are
    kept; only the paper leaves active consideration."""
    cc = _open_store(root).unlink_candidate(claim_id, candidate_id)
    return {"claim_id": claim_id, "candidate_id": candidate_id,
            "remaining_candidates": len(cc.candidates)}
