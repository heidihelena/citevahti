"""Single source of truth for "where is this in the workflow, and what's next".

Read-only: it computes the next human action from the ledger; it never mutates and
never reveals an AI rating the human hasn't earned yet. Every surface — the web panel,
the VS Code extension, the agent prompt, and the future ``citevahti run`` — reads its
phase and its vocabulary from here instead of re-deriving them, so they cannot drift
apart (the divergence the surfaces had: app.js ``phaseOf``, the extension's hardcoded
verdict map, and the prose readiness lines each computed this independently).
"""

from __future__ import annotations

from typing import Optional

from .schemas.report import STATE_CODE, STATE_LABEL  # the canonical five claim states

# ---- vocabulary (one definition; surfaces render it, never hardcode it) ------
# The four verdicts a human can record. The panel keys, the VS Code ACTIONS map, and
# the report codes all derive from this single tuple.
VERDICTS = (
    {"decision": "accept",                "code": "oo", "key": "oo", "label": "Accept"},
    {"decision": "accepted_with_caution", "code": "o",  "key": "o",  "label": "Accept with caution"},
    {"decision": "needs_second_review",   "code": "r",  "key": "r",  "label": "Needs review"},
    {"decision": "reject",                "code": "d",  "key": "d",  "label": "Reject"},
)

# The per-candidate review card walks these in order (Rate → Reveal → Decide → Write).
# "reveal" is a state of the card, not a separate action — exposed as reveal_ready so a
# surface can light the step honestly instead of guessing (the panel showed a "Reveal"
# step its phase function never returned).
PHASES = ("rate", "decide", "write", "done")


def candidate_phase(*, has_human_rating: bool, has_decision: bool, written: bool) -> str:
    """The next action for one (claim, candidate) pair, from durable ledger facts.

    Order: you rate first; then (the AI second opinion revealed) you decide; then, for an
    accept, you write to Zotero; ``done`` once that write is committed.
    """
    if written:
        return "done"
    if not has_human_rating:
        return "rate"
    if not has_decision:
        return "decide"
    return "write"


def reveal_ready(*, has_human_rating: bool, has_ai_rating: bool) -> bool:
    """True once the blinded AI second rating may be shown — only after the human rates."""
    return bool(has_human_rating and has_ai_rating)


def candidate_step(*, has_human_rating: bool, has_ai_rating: bool,
                   has_decision: bool, written: bool) -> dict:
    """The full step descriptor a surface renders for one candidate: the phase, whether
    the AI rating may be revealed, and (when deciding) the verdicts on offer."""
    phase = candidate_phase(has_human_rating=has_human_rating,
                            has_decision=has_decision, written=written)
    return {
        "phase": phase,
        "reveal_ready": reveal_ready(has_human_rating=has_human_rating,
                                     has_ai_rating=has_ai_rating),
        "allowed_verdicts": [dict(v) for v in VERDICTS] if phase == "decide" else [],
    }


def vocabulary() -> dict:
    """The verdicts, states, and phases — served to surfaces so none hardcode them."""
    return {
        "verdicts": [dict(v) for v in VERDICTS],
        "states": [{"state": s, "code": STATE_CODE[s].strip(), "label": STATE_LABEL[s]}
                   for s in STATE_CODE],
        "phases": list(PHASES),
    }


# ---- project-level next action (drives the panel wizard + future `run`) -------
def project_status(root: str, client=None) -> dict:
    """Where the whole project is, and the single next thing the human should do.

    Read-only and degradation-safe (reuses ``start.preflight_snapshot``). The ledger is
    the resumable state — this derives "what's next" fresh each call, so ``run`` and a
    panel wizard resume identically without a separate cursor.
    """
    from .start import preflight_snapshot

    snap = preflight_snapshot(root, client)
    if not snap.get("project_initialized"):
        return {"ready": False, "claims_total": 0, "counts": {}, "blockers": ["not_initialized"],
                "next": {"kind": "init",
                         "label": "Create the project ledger to begin (citevahti init)."}}

    counts = snap.get("claims") or {}
    total = counts.get("total", 0)
    blockers = []
    if not snap.get("zotero_write_ready"):
        # soft: rating and deciding work offline; only the Zotero write needs this.
        blockers.append("zotero_not_write_ready")
    nxt = _next_action(root, total, counts)
    return {"ready": bool(total and nxt["kind"] in ("report", "done")),
            "claims_total": total, "counts": counts, "blockers": blockers, "next": nxt}


def _next_action(root: str, total: int, counts: dict) -> dict:
    if total == 0:
        return {"kind": "add_claims",
                "label": "Add a manuscript — paste a paragraph and CiteVahti extracts its claims."}
    pending = counts.get("needs_support", 0) + counts.get("review_needed", 0)
    if pending:
        return {"kind": "rate", "claim_id": _first_pending_claim(root),
                "label": f"{pending} claim(s) still need your rating or a decision — "
                         "open them in the panel."}
    return {"kind": "report",
            "label": "Every claim is decided — export the citation-integrity report."}


def _first_pending_claim(root: str) -> Optional[str]:
    """The first claim still awaiting a human rating or decision (report order)."""
    from . import tools as engine
    try:
        rep = engine.claim_report(root=root)
    except Exception:  # noqa: BLE001 — never let "what's next" raise
        return None
    for row in rep.rows:
        if row.state in ("needs_support", "review_needed"):
            return row.claim_id
    return None
