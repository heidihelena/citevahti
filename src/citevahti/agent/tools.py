"""The constrained agent tool surface (ADR-0001 + ADR-0002).

Thin, safe wrappers over the engine. Each returns JSON-safe dicts. The dangerous
verbs simply do not exist here: there is no raw Zotero write, no one-call commit,
no way to set the human rating or the final decision, and the AI rating is never
echoed back (blinding). See ``policy.py`` for the contract.
"""

from __future__ import annotations

from typing import Optional

from .. import tools as _t


# ---- bootstrap -------------------------------------------------------------
def init(*, model_id: Optional[str] = None, model_snapshot: Optional[str] = None,
         root: Optional[str] = None) -> dict:
    """Create the project ledger (``.citevahti/config.json``) if it doesn't exist, and
    optionally PIN the agent's model so AI-extracting tools (``propose_claim`` /
    ``propose_revision``) can run.

    Run this FIRST — every other tool needs the ledger. Idempotent. Pass ``model_id``
    (your own model, e.g. ``"claude-opus-4-8"``) to record provenance; the snapshot
    defaults to the model id when not given. Reports the resolved root + config path so
    it's clear WHERE the ledger lives (the server's bound root, not the caller's cwd)."""
    from ..state import CiteVahtiStore
    store = CiteVahtiStore(root or ".")
    already = store.exists()
    if not already:
        store.init()
    pinned = None
    if model_id:
        cfg = store.load_config()
        cfg.ai_provenance.model_id = model_id
        cfg.ai_provenance.model_snapshot = model_snapshot or model_id
        store.save_config(cfg)
        pinned = cfg.ai_provenance.model_id
    return {"status": "already_initialized" if already else "initialized",
            "root": str(store.dir.parent), "config_path": str(store.config_path),
            "model_pinned": pinned}


# ---- read-only -------------------------------------------------------------
def triage(*, root: Optional[str] = None) -> dict:
    """Risk-first triage: the few claims worth attention NOW, worst-first, each with the
    reason + the next action. Read-only. The friendly entry point — present these instead
    of asking the human to review every claim ("review these 3, not all 84")."""
    t = _t.triage(root=root)
    return {"total": t.total, "needs_attention": t.needs_attention, "clean": t.clean,
            "score": t.score, "band": t.band,
            "items": [{"claim_id": it.claim_id, "claim_text": it.claim_text, "state": it.state,
                       "reason": it.reason, "action": it.action, "risk": it.risk,
                       "fatal": it.fatal} for it in t.items]}


def check_paragraph(text: str, *, root: Optional[str] = None) -> dict:
    """Check-a-paragraph: paste a snippet the user just wrote and report, per sentence,
    which claims they've already VETTED, which NEED ATTENTION (with why + next action),
    and which are NEW/untracked. Read-only, no AI — the everyday in-the-writing loop.
    Offer to add + review the new ones; lead them to the ones needing attention."""
    t = _t.check_paragraph(text, root=root)
    return {"total": t.total, "reviewed": t.reviewed, "attention": t.attention, "new": t.new,
            "sentences": [{"text": s.text, "status": s.status, "claim_id": s.claim_id,
                           "state": s.state, "reason": s.reason, "action": s.action}
                          for s in t.sentences]}


def methods(*, root: Optional[str] = None) -> dict:
    """Methods statement: the submission-ready methods paragraph auto-filled with this
    ledger's real numbers, plus the PRISMA-style 'how the literature was found' disclosure
    (whether an LLM was in the discovery loop, and that it only proposed leads — humans
    made every screening and rating decision). Read-only. Offer this for systematic reviews
    and pre-submission; it is the paste-ready methods + AI-use disclosure text."""
    return {"markdown": _t.methods_statement(root=root)}


def status(*, root: Optional[str] = None) -> dict:
    from ..capabilities import CapabilityStatusService
    from ..probe import HttpxClient
    from ..state import CiteVahtiStore
    rep = CapabilityStatusService(CiteVahtiStore(root or "."), HttpxClient()).report()
    return {"connections": {c.name: c.status for c in rep.connections},
            "write_backend": rep.write_backend_kind, "can_write": rep.supported_write_ops,
            "cannot_write": rep.unsupported_write_ops,
            # honest write-target summary so the UI can say what a write will touch
            # before the user commits it (library id is an identifier, not a secret)
            "write_target": {"backend": rep.write_backend_kind,
                             "available": rep.write_backend_available,
                             "zotero_library": rep.zotero_user_id,
                             "permissions": rep.permissions}}


def open_review_panel(port: int = 8765, open_browser: bool = True, *,
                      root: Optional[str] = None) -> dict:
    """Open the human's loopback rating panel (idempotent; loopback-only).

    Closes the no-terminal dead-end: on the desktop-extension install only the
    bare stdio server runs, so when the claim-test prompt reaches the rate-first
    step the agent must be able to bring the rating surface up for the human.
    Adds no rating power — the panel is where the HUMAN rates, blind."""
    from ..start import launch_panel
    res = launch_panel(root or ".", port=port, open_browser=open_browser)
    res.pop("_httpd", None)        # process-local handle, not MCP-serializable
    if res["status"] == "port_conflict":
        res["remediation"] = (f"Port {port} is busy with a non-CiteVahti service; "
                              "retry with another port (e.g. 8766).")
    if res["status"] in ("started", "reused"):
        res["message"] = (f"Rating panel ready at {res['url']} — ask the human to "
                          "record their blind support rating there.")
    return res


def verify_claims(*, root: Optional[str] = None) -> dict:
    """Run citation-integrity tests over the manuscript's claims (read-only 4-state report)."""
    rep = _t.claim_report(root=root)
    return {"total": rep.total, "counts": rep.counts,
            "claims": [{"claim_id": r.claim_id, "state": r.state, "code": r.code.strip(),
                        "claim_text": r.claim_text, "manuscript_location": r.manuscript_location,
                        "candidate_count": r.candidate_count, "accepted_count": r.accepted_count}
                       for r in rep.rows]}


def pubmed_search(query: str, *, max_results: int = 20, root: Optional[str] = None) -> dict:
    """Staged PubMed search. Exact query preserved; results are not citations.

    Fetches abstracts so candidates carry the text the support judgment needs — a
    title alone leaves both the human and the blinded AI unable to rate (they abstain).
    """
    rec = _t.literature_search(query, max_results=max_results, include_abstracts=True, root=root)
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
                "message": "pin the agent's model first — call init(model_id='<your model>') "
                           "(or set it in the panel's ✦ AI settings) before proposing claims"}
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
                "message": "pin the agent's model first — call init(model_id='<your model>') "
                           "(or set it in the panel's ✦ AI settings) before proposing revisions"}
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
    # the most advanced/recent rating for the pair — the SAME selector the panel and
    # report use, so provenance never explains a stale or blank duplicate rating.
    from ..claims.support import select_support_rating
    rating = select_support_rating(store, dec.claim_id, dec.candidate_id)
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


def claim_bond_status(claim_id: str, *, root: Optional[str] = None) -> dict:
    """Read-only: is this claim's evidence assessment still in sync with its text?

    After a claim is revised, ratings/decisions formed against the old wording are
    flagged ``stale`` — a checkable advisory to re-verify, nothing is invalidated."""
    return _t.claim_bond_status(claim_id, root=root)
