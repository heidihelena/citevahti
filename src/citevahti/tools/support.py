"""Claim-support dual-rating + final decision (ADR-0010 PR 1g — ledger-write group).

The (claim, candidate) support workflow: start a blinded support rating, commit the HUMAN
value first, run the AI as a blinded advisory second rater, compare, adjudicate a
discordance, and record the human-owned final ``decide``. Plus the organized-panel
"X of N support" aggregate and the read-only rating/decision loaders.

Blinding and human authority are load-bearing (ADR-0001): the AI never sees the human value,
its support rating is advisory and never decides, and ``decide`` records a human-owned final
only. Those invariants live in the ``claims`` service layer (ClaimSupportEngine /
DecisionService) — these are thin façade wrappers that do not re-implement or relax them
(guarded by test_blinding_deterministic.py, the agent-surface blinding tests, and
test_decision_tamper_integrity.py). Writes only to the local, audited ledger.

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ._common import _open_store, _pubmed_provider


def _support_engine(root, rater=None):
    from ..claims import ClaimSupportEngine
    return ClaimSupportEngine(_open_store(root), rater=rater)


def support_start(claim_id: str, candidate_id: str, *, root: Optional[str] = None):
    """Start a blinded claim-support rating for a (claim, candidate) pair."""
    return _support_engine(root).support_start(claim_id, candidate_id)


def support_commit_human(rating_id: str, value: str, *, fit=None, rationale: Optional[str] = None,
                         committed_by: str = "human", root: Optional[str] = None):
    """Commit + lock the human claim-support value (with optional PICO fit)."""
    return _support_engine(root).support_commit_human(
        rating_id, value, fit=fit, rationale=rationale, committed_by=committed_by)


def support_panel(claim_id: str, candidate_id: Optional[str] = None, *, root: Optional[str] = None):
    """Organized-panel "X of N support" aggregate (ADR-0008): how many of N independent human
    reviewers support a claim, the value distribution, raw agreement, and the confidence tier
    (1 individual · 2–7 review · 8+ guideline). Reads existing human ratings — no new rating,
    no decision. With ``candidate_id`` it summarizes that pair; without, the whole claim."""
    from ..claims.panel import claim_panel_summary, panel_summary
    store = _open_store(root)
    if candidate_id:
        return panel_summary(store, claim_id, candidate_id)
    return claim_panel_summary(store, claim_id)


def support_run_ai(rating_id: str, task_type: str = "assess", *, root: Optional[str] = None,
                   rater=None):
    """Blind advisory AI claim-support rating (needs a pinned model + a rater).

    With no rater injected, build one from config: ``off`` -> a clear error (the MCP
    assistant submits the rating instead), ``local`` / ``api`` -> the configured model.
    """
    store = _open_store(root)
    if rater is None:
        from ..claims import build_support_ai_rater
        rater = build_support_ai_rater(store.load_config())
        if rater is None:
            from ..validators.errors import AIUnavailableError
            raise AIUnavailableError(
                "AI is off — the AI second opinion is optional. Continue human-only "
                "(your rating decides), or turn it on: set 'local' or 'api' in the panel "
                "(✦ AI), or have your MCP assistant submit the rating.")
    _backfill_abstract(store, rating_id, root)   # a title alone -> the AI can only abstain
    return _support_engine(root, rater).support_run_ai(rating_id, task_type)


def _backfill_abstract(store, rating_id: str, root: Optional[str]) -> None:
    """Best-effort: if the candidate has a PMID but no abstract, fetch + save it so the
    AI (and the human) have the text the support judgment needs. Offline/failure: leave
    it as-is and let the rater abstain honestly."""
    try:
        rec = store.load_support_rating(rating_id)
        cc = store.load_candidates(rec.claim_id)
        cand = next((c for c in cc.candidates if c.candidate_id == rec.candidate_id), None)
        if cand is None or getattr(cand, "abstract", None) or not getattr(cand, "pmid", None):
            return
        hits = _pubmed_provider(root).fetch_records([cand.pmid], include_abstracts=True)
        abstract = next((getattr(h, "abstract", None) for h in hits
                         if getattr(h, "abstract", None)), None)
        if abstract:
            cand.abstract = abstract
            store.save_candidates(cc)
    except Exception:  # noqa: BLE001 (enrichment is best-effort; never block the rating)
        pass


def support_compare(rating_id: str, *, root: Optional[str] = None):
    """Compare human vs AI support; concordance locks in the human value."""
    return _support_engine(root).support_compare(rating_id)


def support_adjudicate(rating_id: str, final_value: str, rationale: str, decider: str = "human",
                       *, root: Optional[str] = None):
    """Human/panel adjudication of a discordant support rating (only path to final)."""
    return _support_engine(root).support_adjudicate(rating_id, final_value, rationale, decider)


def get_support_rating(rating_id: str, *, root: Optional[str] = None):
    """Load a claim-support rating (read-only)."""
    return _open_store(root).load_support_rating(rating_id)


# ---- ADR-0001 step 4: final decisions ------------------------------------
def decide(claim_id: str, candidate_id: str, final_decision: str, decision_reason: str, *,
           rating_id: Optional[str] = None, decided_by: str = "human", root: Optional[str] = None):
    """Record the human-owned final decision for a (claim, candidate) pair.

    If the validation warehouse is enabled with auto_emit, a de-identified
    validation record is appended (the label emerges from the workflow)."""
    from ..claims import DecisionService
    store = _open_store(root)
    rec = DecisionService(store).decide(
        claim_id, candidate_id, final_decision, decision_reason,
        rating_id=rating_id, decided_by=decided_by)
    cfg = store.load_config()
    if cfg.validation_warehouse.enabled and cfg.validation_warehouse.auto_emit:
        from ..warehouse import ValidationWarehouseService
        ValidationWarehouseService(store, cfg).emit_for_decision(claim_id, candidate_id)
    return rec


def list_decisions(claim_id: str, *, root: Optional[str] = None):
    """List a claim's final decisions (read-only)."""
    from ..claims import DecisionService
    return DecisionService(_open_store(root)).list_for_claim(claim_id)
