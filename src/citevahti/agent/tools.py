"""The constrained agent tool surface (ADR-0001 + ADR-0002).

Thin, safe wrappers over the engine. Each returns JSON-safe dicts. The dangerous
verbs simply do not exist here: there is no raw Zotero write, no one-call commit,
no way to set the human rating or the final decision, and the AI rating is never
echoed back (blinding). See ``policy.py`` for the contract.
"""

from __future__ import annotations

from typing import Optional

from .. import tools as _t


# ---- read-only -------------------------------------------------------------
def status(*, root: Optional[str] = None) -> dict:
    from ..capabilities import CapabilityStatusService
    from ..probe import HttpxClient
    from ..state import CiteVahtiStore
    rep = CapabilityStatusService(CiteVahtiStore(root or "."), HttpxClient()).report()
    return {"connections": {c.name: c.status for c in rep.connections},
            "write_backend": rep.write_backend_kind, "can_write": rep.supported_write_ops,
            "cannot_write": rep.unsupported_write_ops}


def verify_claims(*, root: Optional[str] = None) -> dict:
    """Run citation-integrity tests over the manuscript's claims (read-only 4-state report)."""
    rep = _t.claim_report(root=root)
    return {"total": rep.total, "counts": rep.counts,
            "claims": [{"claim_id": r.claim_id, "state": r.state, "code": r.code.strip(),
                        "claim_text": r.claim_text, "manuscript_location": r.manuscript_location,
                        "candidate_count": r.candidate_count, "accepted_count": r.accepted_count}
                       for r in rep.rows]}


def pubmed_search(query: str, *, max_results: int = 20, root: Optional[str] = None) -> dict:
    """Staged PubMed search. Exact query preserved; results are not citations."""
    rec = _t.literature_search(query, max_results=max_results, root=root)
    return {
        "batch_id": rec.batch_id, "status": rec.status, "exact_query": rec.exact_query,
        "query_translation": rec.query_translation, "total_matched": rec.total_count,
        "returned": rec.result_count, "review_required": bool(getattr(rec, "review_required", False)),
        "warnings": rec.warnings, "error_code": rec.error_code, "remediation": rec.remediation,
        "hits": [{"record_id": h.record_id, "pmid": h.pmid, "doi": h.doi, "title": h.title,
                  "year": h.year, "journal": h.journal, "dedupe_status": h.dedupe_status}
                 for h in rec.hits],
    }


# ---- propose / link --------------------------------------------------------
def propose_claim(text: str, claim_type: str = "other", *,
                  manuscript_location: Optional[str] = None, root: Optional[str] = None) -> dict:
    """Record an AI-proposed claim (flagged ai-extracted; the human confirms)."""
    from ..state import CiteVahtiStore
    model = CiteVahtiStore(root or ".").load_config().ai_provenance.model_id
    if "PENDING" in (model or ""):
        return {"error": "model_not_pinned",
                "message": "configure ai_provenance (the agent's model) before proposing claims"}
    c = _t.add_claim(text, claim_type, manuscript_location=manuscript_location,
                     extracted_by="ai", extraction_model=model, root=root)
    return {"claim_id": c.claim_id, "claim_type": c.claim_type,
            "status": "proposed", "note": "ai-extracted; awaiting human confirmation"}


def propose_revision(claim_id: str, new_text: str, *, root: Optional[str] = None) -> dict:
    """Suggest a claim rewrite (flagged ai-proposed). Applies NOTHING — the human
    reviews the diff and accepts; the agent cannot accept its own rewrite."""
    from ..state import CiteVahtiStore
    model = CiteVahtiStore(root or ".").load_config().ai_provenance.model_id
    if "PENDING" in (model or ""):
        return {"error": "model_not_pinned",
                "message": "configure ai_provenance (the agent's model) before proposing revisions"}
    try:
        c = _t.propose_revision(claim_id, new_text, extracted_by="ai",
                                extraction_model=model, root=root)
    except ValueError as e:
        return {"error": "invalid_revision", "message": str(e)}
    return {"claim_id": c.claim_id, "status": "proposed",
            "note": "ai-suggested rewrite; awaiting human review of the diff (human accepts)"}


def link_candidates(claim_id: str, intake_batch_id: str, *,
                    record_ids: Optional[list] = None, root: Optional[str] = None) -> dict:
    rep = _t.link_candidates(claim_id, intake_batch_id, record_ids=record_ids, root=root)
    return {"claim_id": rep.claim_id, "linked": rep.linked,
            "skipped_duplicates": rep.skipped_duplicates, "total_candidates": rep.total_candidates}


# ---- blinded support rating (agent rates; value never echoed back) ---------
def start_support_rating(claim_id: str, candidate_id: str, *, root: Optional[str] = None) -> dict:
    from ..claims import ClaimSupportEngine
    from ..state import CiteVahtiStore
    rec = ClaimSupportEngine(CiteVahtiStore(root or ".")).support_start(claim_id, candidate_id)
    return {"rating_id": rec.rating_id, "claim_id": claim_id, "candidate_id": candidate_id,
            "status": "started", "blinded": True}


def submit_ai_support_rating(rating_id: str, value: str, *, confidence: Optional[float] = None,
                             fit: Optional[dict] = None, reasoning: Optional[str] = None,
                             root: Optional[str] = None) -> dict:
    """Record the agent's own support rating, BLIND. The value is NOT echoed back —
    it stays hidden until the human submits their independent rating."""
    from ..claims import ClaimSupportEngine
    from ..state import CiteVahtiStore
    ClaimSupportEngine(CiteVahtiStore(root or ".")).submit_ai_rating(
        rating_id, value, confidence=confidence, fit=fit, reasoning=reasoning)
    return {"rating_id": rating_id, "recorded": True, "blinded": True,
            "message": "AI rating recorded and hidden until the human submits theirs"}


# ---- guarded write: preview -> commit(token) -> undo -----------------------
def _dedupe_status(warnings) -> str:
    for w in warnings or []:
        if "already in the Zotero library" in w:
            return "duplicate"
        if "dedupe_unverified" in w:
            return "dedupe_unverified"
    return "ok"


def preview_write(decision_id: str, *, collection_key: Optional[str] = None,
                  root: Optional[str] = None) -> dict:
    """Preview the decision-gated write. Returns an approval token + dedupe status.
    The agent CANNOT write without first calling this and passing the token back."""
    diff = _t.commit_decision(decision_id, collection_key=collection_key, dry_run=True, root=root)
    return {"approval_token": diff.confirm_token, "proposed_changes": diff.proposed_changes,
            "backend_available": diff.backend_available, "collection_key": collection_key,
            "dedupe_status": _dedupe_status(diff.warnings), "warnings": diff.warnings}


def commit_write(decision_id: str, approval_token: str, *, collection_key: Optional[str] = None,
                 allow_unverified_dedupe: bool = False, root: Optional[str] = None) -> dict:
    """Write ONLY the payload approved by ``approval_token`` from a prior preview."""
    txn = _t.commit_decision(decision_id, collection_key=collection_key, dry_run=False,
                             confirm_token=approval_token,
                             allow_unverified_dedupe=allow_unverified_dedupe, root=root)
    res = txn.result or {}
    return {"status": txn.status, "transaction_id": getattr(txn, "transaction_id", None),
            "created_keys": res.get("created_keys", []), "collection_key": txn.collection_key,
            "error_code": txn.error_code, "remediation": txn.remediation,
            "undo_available": txn.status == "committed"}


def undo(transaction_id: str, *, root: Optional[str] = None) -> dict:
    txn = _t.undo_transaction(transaction_id, root=root)
    return {"status": txn.status, "transaction_id": txn.transaction_id,
            "deleted_keys": (txn.result or {}).get("undo", {}).get("deleted_keys", []),
            "error_code": txn.error_code}


def get_provenance(decision_id: str, *, root: Optional[str] = None) -> dict:
    """The "why is this here?" chain for a decision — with the AI rating BLINDED
    until the human has submitted their independent rating."""
    from ..state import CiteVahtiStore
    store = CiteVahtiStore(root or ".")
    dec = store.load_decision(decision_id)
    claim = store.load_claim(dec.claim_id)
    cand = next((c for c in store.load_candidates(dec.claim_id).candidates
                 if c.candidate_id == dec.candidate_id), None)
    rating = None
    for rid in store.list_support_ratings():
        r = store.load_support_rating(rid)
        if r.claim_id == dec.claim_id and r.candidate_id == dec.candidate_id:
            rating = r
    human_v = rating.human_rating.value if (rating and rating.human_rating) else None
    ai_v = (rating.ai_rating.value if (rating and rating.ai_rating) else None)
    ai_shown = ai_v if human_v is not None else ("hidden (blinded until human rates)"
                                                 if ai_v is not None else None)
    txn_id = None
    for tid in store.list_transactions():
        t = store.load_transaction(tid)
        if t.candidate_id == dec.candidate_id and t.status in ("committed", "undone"):
            txn_id = t.transaction_id
    return {
        "claim_id": dec.claim_id, "claim_text": claim.claim_text, "claim_type": claim.claim_type,
        "pmid": getattr(cand, "pmid", None), "doi": getattr(cand, "doi", None),
        "title": getattr(cand, "title", None),
        "retrieval_query": getattr(cand, "retrieval_query", None),
        "why_found": getattr(cand, "why_found", None),
        "support": {"human": human_v, "ai": ai_shown, "final": dec.final_support_status},
        "final_decision": dec.final_decision, "agreement": dec.agreement_status,
        "transaction_id": txn_id, "undo_available": txn_id is not None,
    }
