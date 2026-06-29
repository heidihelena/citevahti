"""A thin, loopback-only HTTP API for the CiteVahti side panel (ADR-0007).

Scope is deliberately tiny: just enough to wire the inline decision card to engine
state. It is NOT a manuscript editor and NOT a dashboard. Every handler delegates
to an existing function:

  - reads/claims  -> ``citevahti.tools`` (the engine)
  - human rating  -> ``citevahti.tools.support_*`` / ``decide`` (human-owned)
  - writes        -> ``citevahti.agent.tools`` (the token-gated, blinded wrappers)

Safety properties (asserted by tests):
  * binds to ``127.0.0.1`` by default; never exposed externally.
  * a read endpoint never reveals the AI rating before a human rating exists.
  * the write path has no raw Zotero verb: preview returns a token, commit needs it.
  * introduces no new agent capability (``agent.TOOLS`` is untouched).
  * no telemetry, no cloud calls.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
import uuid
from html import escape as esc_html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .. import agent
from .. import tools as engine
from .. import workflow
from ..claims.bonds import claim_bond_status
from ..claims.panel import panel_summary
from . import manuscript as M
from . import prefs

WEB_DIR = Path(__file__).parent / "web"
_STATIC = {"/": "index.html", "/index.html": "index.html",
           "/state.js": "state.js", "/api.js": "api.js",  # loaded before app.js
           "/app.js": "app.js", "/styles.css": "styles.css",
           "/favicon.svg": "favicon.svg",
           "/favicon.ico": "favicon.svg",  # browsers auto-request /favicon.ico; serve the SVG
           "/apple-touch-icon.png": "apple-touch-icon.png",  # iOS home screen / bookmarks
           "/apple-touch-icon-precomposed.png": "apple-touch-icon.png"}  # older iOS variant
_CONTENT_TYPE = {".html": "text/html; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".svg": "image/svg+xml",
                 ".png": "image/png"}


# ---- blinding ---------------------------------------------------------------
def blinded_rating_view(record) -> dict:
    """Project a support rating for the panel, keeping the AI value hidden until a
    human rating exists (the same rule the engine + ``get_provenance`` enforce).

    The human may always see their own rating; the AI rating is only revealed once
    the human has committed theirs.
    """
    from ..rating.blinding import blinded_ai_value
    human = record.human_rating.value if record.human_rating else None
    ai_value = record.ai_rating.value if record.ai_rating else None
    ai_present = record.ai_rating is not None
    # the one canonical blinding rule (see rating/blinding.py) — never re-derive it here
    ai_shown = blinded_ai_value(human, ai_value, hidden="hidden (blinded until human rates)")
    human_fit = (record.human_rating.fit.model_dump()
                 if record.human_rating and record.human_rating.fit else None)
    return {
        "rating_id": record.rating_id,
        "claim_id": record.claim_id,
        "candidate_id": record.candidate_id,
        "human": human,
        "human_fit": human_fit,
        "ai": ai_shown,
        "ai_present": ai_present,
        "comparison_status": record.comparison.status,
        "final_value": record.adjudication.final_value,
        "adjudication_event": record.adjudication.event,
    }


def _find_rating_for(store, claim_id: str, candidate_id: str):
    # the most advanced/recent rating for a pair (support_start mints a new id each
    # call) — one shared selector so the panel, report, and agent provenance agree.
    from ..claims.support import select_support_rating
    return select_support_rating(store, claim_id, candidate_id)


def _candidate_card(c) -> dict:
    return {
        "candidate_id": c.candidate_id, "pmid": c.pmid, "doi": c.doi,
        "title": c.title, "journal": c.journal, "year": c.year,
        "retrieval_query": c.retrieval_query, "why_found": c.why_found,
        "already_in_zotero": c.already_in_zotero, "dedupe_status": c.dedupe_status,
        "abstract": getattr(c, "abstract", None),
        # reuse rights (from the licence scan) — reported, never a reuse verdict
        "oa_status": getattr(c, "oa_status", None), "license": getattr(c, "license", None),
    }


def _evidence_basis(rec, candidate) -> str:
    """What the support judgment can be based on, shown on the review card at rate time:
    a located full-text passage (someone anchored a quote), the candidate's abstract only,
    or no text staged. Same rule as the methods statement's evidence-basis line — a rating
    with a quoted PassageRef is full-text-anchored; otherwise the rater sees the abstract."""
    human = rec.human_rating.source_passages if (rec and rec.human_rating) else []
    ai = rec.ai_rating.supporting_passages if (rec and rec.ai_rating) else []
    if human or ai:
        return "full_text"
    return "abstract_only" if getattr(candidate, "abstract", None) else "no_text"


def _evidence_index(root: str, claim_id: str) -> dict:
    """PICO fit + excerpt + blinded AI per candidate, from the read-only report.

    The report already computes these blinding-safely: ``fit``/``fit_total``/
    ``excerpt`` come only from the human's committed rating, and ``ai_support`` is
    "hidden" until the human rates. We reuse it rather than re-derive blinding."""
    rep = engine.claim_report(claim_ids=[claim_id], root=root)
    out = {}
    for row in rep.rows:
        for ev in row.evidence:
            out[ev.candidate_id] = {
                "fit": ev.fit.model_dump() if ev.fit else None,
                "fit_total": ev.fit_total,
                "excerpt": ev.excerpt,
                "ai_support": ev.ai_support,        # blinded "hidden" until human rates
                "support_status": ev.support_status,
                "final_decision": ev.final_decision,
                "agreement": ev.agreement,
                "decision_id": ev.decision_id,
            }
    return out


# ---- pending OAuth request-token secrets: in-process only, with a TTL --------
# These temporary secrets MUST NOT touch disk (panel.json carries no secrets — see
# prefs.py). They live in this process between /oauth/start and the loopback
# callback, which are handled by the same panel process.
_OAUTH_PENDING: dict = {}
_OAUTH_TTL_SECONDS = 600


def _oauth_pending_sweep() -> None:
    now = time.time()
    for k in [k for k, (_, exp) in list(_OAUTH_PENDING.items()) if exp < now]:
        _OAUTH_PENDING.pop(k, None)


def _oauth_pending_put(token: str, secret: str) -> None:
    _oauth_pending_sweep()
    _OAUTH_PENDING[token] = (secret, time.time() + _OAUTH_TTL_SECONDS)


def _oauth_pending_take(token: str):
    _oauth_pending_sweep()
    entry = _OAUTH_PENDING.pop(token, None)
    return entry[0] if entry else None


# ---- per-claim audit trail (decisions + Zotero write transactions) ----------
def _claim_history(root: str, claim_id: str) -> dict:
    """The claim's recorded decisions and Zotero write transactions, as a timeline.

    Read-only and audit-faithful: every decision and write is shown with who/when
    and (for writes) whether it was undone — the 'auditable claim-evidence trail'."""
    decisions = [{"decision_id": d.decision_id, "candidate_id": d.candidate_id,
                  "final_decision": d.final_decision, "final_support_status": d.final_support_status,
                  "agreement_status": getattr(d, "agreement_status", None),
                  "decided_by": d.decided_by, "reason": d.decision_reason,
                  "at": d.created_at, "audit_event_id": getattr(d, "audit_event_id", None)}
                 for d in engine.list_decisions(claim_id, root=root)]
    store = engine._open_store(root)
    try:
        cand_ids = {c.candidate_id for c in store.load_candidates(claim_id).candidates}
    except Exception:  # noqa: BLE001
        cand_ids = set()
    txns = []
    for t in engine.list_transactions(root=root):
        if getattr(t, "candidate_id", None) in cand_ids or getattr(t, "claim_id", None) == claim_id:
            res = t.result or {}
            txns.append({"transaction_id": t.transaction_id, "status": t.status,
                         "candidate_id": getattr(t, "candidate_id", None),
                         "keys": res.get("created_keys") or res.get("deleted_keys"),
                         "at": t.committed_at or t.created_at, "undone_at": t.undone_at})
    return {"claim_id": claim_id, "decisions": decisions, "transactions": txns}


def _written_candidates(root: str, claim_id: str) -> set:
    """Candidate ids for this claim with a committed, not-yet-undone Zotero write — the
    durable 'done' signal the per-candidate step uses (survives navigating away)."""
    try:
        cand_ids = {c.candidate_id for c in engine._open_store(root).load_candidates(claim_id).candidates}
    except Exception:  # noqa: BLE001
        return set()
    out = set()
    for t in engine.list_transactions(root=root):
        cid = getattr(t, "candidate_id", None)
        if cid in cand_ids and t.status == "committed" and not getattr(t, "undone_at", None):
            out.add(cid)
    return out


# ---- manuscript grouping ----------------------------------------------------
def _manuscript_groups(root: str) -> dict:
    """Group claim-report rows by manuscript_id (the file part of the location)."""
    rep = engine.claim_report(root=root)
    groups: dict[str, list] = {}
    for r in rep.rows:
        mid = M.parse_location(r.manuscript_location)[0] or "(unlocated)"
        groups.setdefault(mid, []).append(r)
    return groups


def _row_claim(r) -> dict:
    return {"claim_id": r.claim_id, "claim_text": r.claim_text,
            "manuscript_location": r.manuscript_location}


def _claim_state(r) -> dict:
    out = {"state": r.state, "code": r.code.strip(),
           "candidate_count": r.candidate_count, "accepted_count": r.accepted_count,
           "has_stale_bonds": r.has_stale_bonds}
    cite = _accepted_cite(r)
    if cite:
        out["cite"] = cite          # accepted candidate's identifiers → citation-on-copy
    return out


# A claim is a "cited passage" once it has an accepted, supporting candidate; expose
# that candidate's identifiers so copying the claim text can carry its citation.
_ACCEPTED_DECISIONS = {"accept", "accepted_with_caution"}


def _accepted_cite(r) -> Optional[dict]:
    for ev in r.evidence:
        if ev.final_decision in _ACCEPTED_DECISIONS and (ev.title or ev.doi or ev.pmid):
            return {"title": ev.title, "doi": ev.doi, "pmid": ev.pmid}
    return None


# ---- stable error codes + plain remediation (for users AND agents) ----------
# Every error response has the shape {error, code, message, remediation}. The code
# is stable for automation; the remediation is one plain sentence for humans.
_REMEDIATION = {
    "not_initialized": "Run `citevahti init` in the project folder, or switch to a ledger that has one.",
    "invalid_key": "Create a write-enabled Zotero key and connect again (paste it or use OAuth).",
    "api_unreachable": "Check your connection; for Zotero, make sure the desktop app is running.",
    "not_configured": "Set CITEVAHTI_ZOTERO_OAUTH_CLIENT_KEY/SECRET, or paste an API key instead.",
    "missing_field": "A required field was not provided — check the request and try again.",
    "parse_error": "The references could not be parsed — check the format (CSV / RIS / BibTeX).",
    "stale_preview": "The file changed since the preview — preview again so the edit applies to the current text.",
    "support_rule": "Follow the rate → reveal → decide order; adjudicate a disagreement before deciding.",
    "decision_rule": "Resolve the support rating first (rate, then adjudicate a discordance), then decide.",
    "candidate_decided": "Undo the decision (and any Zotero write) before unlinking this paper.",
    "candidate_not_linked": "Reload the claim — this paper is no longer one of its candidates.",
}
_CODE_BY_TYPE = {
    "ValidationError": "invalid_input", "ManualParseError": "parse_error",
    "ClaimSupportError": "support_rule", "DecisionError": "decision_rule",
    "ProbeTransportError": "api_unreachable",
}


def _error_payload(e) -> tuple:
    """Map an exception to (status, {error, code, message, remediation})."""
    if isinstance(e, HttpError):
        code = e.code or "bad_request"
        return e.status, {"error": "bad_request", "code": code, "message": e.message,
                          "remediation": e.remediation or _REMEDIATION.get(code, "")}
    if isinstance(e, KeyError):
        return 400, {"error": "missing_field", "code": "missing_field",
                     "message": str(e), "remediation": _REMEDIATION["missing_field"]}
    msg = str(e)
    code = getattr(e, "code", None)
    if not code:
        code = ("not_initialized" if (isinstance(e, ValueError) and "init" in msg.lower())
                else _CODE_BY_TYPE.get(type(e).__name__, "error"))
    return 400, {"error": type(e).__name__, "code": code, "message": msg,
                 "remediation": _REMEDIATION.get(code, "")}


# ---- routing (pure; unit-testable without sockets) --------------------------
class HttpError(Exception):
    def __init__(self, status: int, message: str, *, code: str = "", remediation: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.remediation = remediation


def dispatch(root: str, method: str, path: str, body: Optional[dict]) -> tuple[int, dict]:
    """Route one API call to an existing engine/agent function.

    Returns ``(status_code, payload)``. Raises nothing — engine errors become a
    4xx/5xx JSON ``{"error": ...}`` so the panel degrades honestly.
    """
    body = body or {}
    try:
        # ---- reads ----------------------------------------------------------
        if method == "GET" and path == "/api/health":
            return 200, agent.tools.status(root=root)

        if method == "GET" and path == "/api/claims":
            rep = engine.claim_report(root=root)
            return 200, {"total": rep.total, "counts": rep.counts,
                         "claims": [{"claim_id": r.claim_id, "state": r.state,
                                     "code": r.code.strip(), "claim_text": r.claim_text,
                                     "manuscript_location": r.manuscript_location,
                                     "candidate_count": r.candidate_count,
                                     "accepted_count": r.accepted_count}
                                    for r in rep.rows]}

        if method == "POST" and path == "/api/claims":
            claim = engine.add_claim(_req(body, "claim_text"), body.get("claim_type", "other"),
                                     manuscript_id=body.get("manuscript_id"),
                                     manuscript_location=body.get("manuscript_location"), root=root)
            return 200, {"claim_id": claim.claim_id}

        m = re.fullmatch(r"/api/claims/([^/]+)/history", path)
        if method == "GET" and m:
            return 200, _claim_history(root, m.group(1))

        # Edit the claim wording in the LEDGER (audited revision). Used when the
        # manuscript file isn't open, so a reviewer can refine the claim after
        # reading the evidence without first locating the .md. When the file IS
        # open the UI uses the previewed document write-back instead, which keeps
        # the .md and the ledger in sync.
        m = re.fullmatch(r"/api/claims/([^/]+)/revise", path)
        if method == "POST" and m:
            claim_id = m.group(1)
            replacement = _req(body, "replacement")
            # Refuse a ledger-only revise when the manuscript file IS open: writing
            # the ledger alone would desync it from the .md. Route to the previewed
            # document write-back instead (which updates both). Only the no-file case
            # falls through to the audited ledger revise.
            claim = engine._open_store(root).load_claim(claim_id)
            if M.resolve_path(prefs.get_manuscripts_dir(root), claim.manuscript_id) is not None:
                raise HttpError(409, "the manuscript file is open — use the previewed document edit "
                                "so the .md and the ledger stay in sync",
                                code="document_open",
                                remediation="Preview and confirm the edit in the document "
                                            "(POST /api/document/preview-edit), not the ledger-only revise.")
            engine.propose_revision(claim_id, replacement, root=root)
            engine.accept_revision(claim_id, root=root)
            claim = engine._open_store(root).load_claim(claim_id)
            return 200, {"claim_id": claim_id, "claim_text": claim.claim_text}

        m = re.fullmatch(r"/api/claims/([^/]+)", path)
        if method == "GET" and m:
            claim_id = m.group(1)
            store = engine._open_store(root)
            claim = store.load_claim(claim_id)
            try:
                cands = store.load_candidates(claim_id).candidates
            except Exception:
                cands = []
            evidence = _evidence_index(root, claim_id)
            written = _written_candidates(root, claim_id)   # committed, not-undone Zotero writes
            # Bond freshness per candidate: an assessment formed against an older
            # claim wording (claim revised since) is flagged so the human re-checks.
            bonds = claim_bond_status(store, claim_id)
            stale_cands = {b["candidate_id"] for b in bonds["bonds"] if b["status"] == "stale"}
            cand_views = []
            for c in cands:
                view = _candidate_card(c)
                rec = _find_rating_for(store, claim_id, c.candidate_id)
                view["rating"] = blinded_rating_view(rec) if rec else None
                ev = evidence.get(c.candidate_id)
                view["evidence"] = ev
                view["evidence_basis"] = _evidence_basis(rec, c)   # abstract-only vs full-text, at rate time
                view["stale_bond"] = c.candidate_id in stale_cands
                # the workflow phase is computed in ONE place (workflow.candidate_step);
                # surfaces render it rather than re-deriving the rate→decide→write rules.
                view["step"] = workflow.candidate_step(
                    has_human_rating=bool(rec and rec.human_rating
                                          and rec.human_rating.value is not None),
                    has_ai_rating=bool(rec and rec.ai_rating is not None),
                    has_decision=bool(ev and ev.get("decision_id")),
                    written=c.candidate_id in written)
                # Organized-panel "X of N support" (ADR-0008) — only when 2+ independent
                # human reviewers rated this pair, so a single-rater claim shows no badge.
                ps = panel_summary(store, claim_id, c.candidate_id)
                view["panel"] = ps if ps["n_raters"] >= 2 else None
                cand_views.append(view)
            return 200, {"claim": {"claim_id": claim.claim_id, "claim_text": claim.claim_text,
                                   "claim_type": claim.claim_type,
                                   "manuscript_location": claim.manuscript_location,
                                   # same key the switcher groups by, so the client can tell
                                   # which manuscript this claim belongs to and switch to it
                                   "manuscript_id": M.parse_location(claim.manuscript_location)[0] or "(unlocated)",
                                   "extracted_by": claim.extracted_by,
                                   "proposed_revision": claim.proposed_revision,
                                   "has_stale_bonds": bonds["has_stale_bonds"]},
                         "candidates": cand_views}

        m = re.fullmatch(r"/api/ratings/([^/]+)", path)
        if method == "GET" and m:
            rec = engine.get_support_rating(m.group(1), root=root)
            return 200, blinded_rating_view(rec)

        m = re.fullmatch(r"/api/decisions/([^/]+)/provenance", path)
        if method == "GET" and m:
            # reuse the agent wrapper: already blinded until the human has rated
            return 200, agent.tools.get_provenance(m.group(1), root=root)

        # ---- human-owned mutations -----------------------------------------
        if method == "POST" and path == "/api/ratings/start":
            rec = engine.support_start(_req(body, "claim_id"), _req(body, "candidate_id"),
                                       root=root)
            return 200, {"rating_id": rec.rating_id, "claim_id": rec.claim_id,
                         "candidate_id": rec.candidate_id, "blinded": True}

        m = re.fullmatch(r"/api/ratings/([^/]+)/human", path)
        if method == "POST" and m:
            rating_id = m.group(1)
            fit = body.get("fit")
            if isinstance(fit, dict):
                from ..schemas.claim_support import FitScores
                fit = FitScores(**fit)
            engine.support_commit_human(rating_id, _req(body, "value"), fit=fit,
                                        rationale=body.get("rationale"),
                                        committed_by=body.get("committed_by", "human"),
                                        root=root)
            # compute concordance now (safe: reveals AI only because the human exists)
            engine.support_compare(rating_id, root=root)
            return 200, blinded_rating_view(engine.get_support_rating(rating_id, root=root))

        # CiteVahti's OWN AI second opinion (local / api). Off-mode -> a clear 4xx;
        # the MCP assistant path (submit_ai_support_rating) is unchanged. Recorded
        # blind — the view hides the AI value until a human rating exists.
        m = re.fullmatch(r"/api/ratings/([^/]+)/run-ai", path)
        if method == "POST" and m:
            engine.support_run_ai(m.group(1), body.get("task_type", "assess"), root=root)
            return 200, blinded_rating_view(engine.get_support_rating(m.group(1), root=root))

        m = re.fullmatch(r"/api/ratings/([^/]+)/adjudicate", path)
        if method == "POST" and m:
            rec = engine.support_adjudicate(m.group(1), _req(body, "final_value"),
                                            _req(body, "rationale"),
                                            body.get("decider", "human"), root=root)
            return 200, blinded_rating_view(rec)

        if method == "POST" and path == "/api/decisions":
            rec = engine.decide(_req(body, "claim_id"), _req(body, "candidate_id"),
                                _req(body, "final_decision"), _req(body, "decision_reason"),
                                rating_id=body.get("rating_id"), decided_by="human", root=root)
            return 200, {"decision_id": rec.decision_id, "claim_id": rec.claim_id,
                         "candidate_id": rec.candidate_id,
                         "final_decision": rec.final_decision,
                         "final_support_status": rec.final_support_status}

        # ---- guarded write: reuse the token-gated agent wrappers ------------
        if method == "POST" and path == "/api/writes/preview":
            return 200, agent.tools.preview_write(
                _req(body, "decision_id"), collection_key=body.get("collection_key"), root=root)

        if method == "POST" and path == "/api/writes/commit":
            return 200, agent.tools.commit_write(
                _req(body, "decision_id"), _req(body, "approval_token"),
                collection_key=body.get("collection_key"),
                allow_unverified_dedupe=bool(body.get("allow_unverified_dedupe", False)),
                root=root)

        if method == "POST" and path == "/api/writes/undo":
            return 200, agent.tools.undo(_req(body, "transaction_id"), root=root)

        # ---- onboarding context + ledger discovery -------------------------
        if method == "GET" and path == "/api/context":
            rep = engine.claim_report(root=root)
            return 200, {"root": str(Path(root).expanduser()),
                         "claim_total": rep.total,
                         "manuscripts_dir": prefs.get_manuscripts_dir(root),
                         "vocabulary": workflow.vocabulary()}   # verdicts/states/phases (single source)

        # project-level "what's next" — the one next action for the whole project,
        # computed in the resolver. Drives the panel wizard and (later) `citevahti run`.
        if method == "GET" and path == "/api/next":
            return 200, workflow.project_status(root)

        # the citation-integrity report as Markdown, so the wizard's final step can hand
        # the never-touched-a-terminal user a file without `citevahti report`. It carries a
        # generation timestamp + the hash-chained audit head (intact?) — a verifiable record
        # that this review work was done, in this order, by the human.
        if method == "GET" and path == "/api/report":
            from ..report import render_html, render_markdown
            rep = engine.claim_report(root=root)
            p = rep.provenance
            return 200, {"markdown": render_markdown(rep), "html": render_html(rep),
                         "total": rep.total, "generated_at": rep.generated_at,
                         "audit_intact": getattr(p, "audit_chain_intact", None),
                         "audit_entries": getattr(p, "audit_entries", None),
                         "audit_head": getattr(p, "audit_head_hash", None)}

        # risk-first triage: the few claims worth attention now, worst-first (read-only).
        if method == "GET" and path == "/api/triage":
            return 200, engine.triage(root=root).model_dump()

        # user-initiated update check: ONE outbound call to PyPI, made only when this
        # endpoint is hit (the panel calls it on a button click, never on load), so it
        # doesn't weaken the local-first/no-silent-egress posture. Read-only, no install.
        if method == "GET" and path == "/api/check-update":
            return 200, engine.check_update()

        if method == "POST" and path == "/api/report/packet":
            return 200, engine.export_review_packet(root=root)

        if method == "POST" and path == "/api/report/docx":
            return 200, engine.export_report_docx(root=root)

        if method == "POST" and path == "/api/manuscripts/import-docx":
            return 200, engine.import_manuscript_docx(_req(body, "docx_base64"), root=root)

        # the ready-to-paste run_claim_tests choreography, pre-filled with the
        # imported/pasted manuscript — closes the .docx → claims handoff into chat
        if method == "POST" and path == "/api/claim-tests-prompt":
            return 200, engine.claim_tests_prompt(body.get("manuscript") or "")

        # the ready-to-paste screen_topic choreography (ADR-0008, Layer 0) — turns a topic
        # into candidate claims + nearby evidence to paste into chat (leads, not verdicts)
        if method == "POST" and path == "/api/topic-screen-prompt":
            return 200, engine.topic_screen_prompt(body.get("topic") or "")

        # ---- the prompt panel: every preprogrammed agent skill in one place -----
        # The panel surfaces the canonical MCP prompts as one-click, copy-to-paste
        # skills (the same text the chat client / desktop chat would run). Read-only
        # text; the deprecated review_manuscript alias is omitted.
        if method == "GET" and path == "/api/prompts":
            from .. import writing
            from ..agent import prompts as P
            items = [
                {"name": P.CLAIM_TEST_PROMPT_NAME, "label": "Run claim tests", "group": "Review",
                 "description": P.CLAIM_TEST_PROMPT_DESCRIPTION,
                 "text": P.run_claim_tests_prompt()},
                {"name": P.SCREEN_TOPIC_PROMPT_NAME, "label": "Screen a topic", "group": "Review",
                 "description": P.SCREEN_TOPIC_PROMPT_DESCRIPTION,
                 "text": P.screen_topic_prompt()},
                {"name": P.CHECK_PARAGRAPH_PROMPT_NAME, "label": "Check a paragraph", "group": "Review",
                 "description": P.CHECK_PARAGRAPH_PROMPT_DESCRIPTION,
                 "text": P.check_paragraph_prompt()},
                {"name": P.METHODS_PROMPT_NAME, "label": "Methods statement", "group": "Review",
                 "description": P.METHODS_PROMPT_DESCRIPTION,
                 "text": P.methods_prompt()},
            ]
            # writing-assistance skills (advisory; suggestion-only, no silent manuscript edit)
            items.extend(writing.writing_skills())
            return 200, {"prompts": items}

        # the researcher's ACCEPTED claims + citekeys, so "Draft from claims" drafts from
        # vetted claims without pasting. Read-only; uncited accepted claims are flagged.
        if method == "GET" and path == "/api/draft-context":
            return 200, engine.draft_context(root=root)

        # ---- small chat with the configured model (local Ollama / LM Studio / API key) ----
        # Advisory text only — records nothing, calls no tools, writes nothing. ai_off when
        # no model is configured. Reuses the same connection plumbing as the AI rater.
        if method == "POST" and path == "/api/chat":
            return 200, engine.chat(body.get("message") or "", root=root)

        # ---- the manuscript "unit test" suite (each claim is a test case) ----
        # Offline by default (instant, structural); online verifies citations are
        # real + not retracted. Optionally scoped to one manuscript.
        if method == "POST" and path == "/api/test-suite":
            online = bool(body.get("online", False))
            mid = body.get("manuscript_id")
            claim_ids = None
            if mid:
                rows = _manuscript_groups(root).get(mid, [])
                claim_ids = [r.claim_id for r in rows]
            return 200, engine.run_manuscript_tests(root=root, online=online, claim_ids=claim_ids)

        if method == "GET" and path == "/api/ledgers":
            return 200, {"active": str(Path(root).expanduser()),
                         "ledgers": prefs.discover_ledgers(root)}

        # audit-chain integrity: recompute the hash chain and report whether the
        # append-only decision log has been tampered with (the trust signal).
        if method == "GET" and path == "/api/audit/verify":
            store = engine._open_store(root)
            return 200, {"intact": bool(store.audit.verify()),
                         "entries": len(store.audit.entries())}

        # ---- de-identified warehouse (local, opt-in, default-off) -----------
        if method == "GET" and path == "/api/warehouse":
            s = engine.warehouse_status(root=root)
            return 200, {"enabled": s.enabled, "include_claim_text": s.include_claim_text,
                         "record_count": s.record_count}

        if method == "POST" and path == "/api/warehouse/configure":
            s = engine.warehouse_configure(enabled=body.get("enabled"),
                                           include_claim_text=body.get("include_claim_text"),
                                           auto_emit=body.get("auto_emit"),
                                           domain=body.get("domain"), root=root)
            return 200, {"enabled": s.enabled, "include_claim_text": s.include_claim_text,
                         "record_count": s.record_count}

        if method == "POST" and path == "/api/warehouse/export":
            s = engine.warehouse_export(root=root)
            return 200, {"output_file": s.output_file, "record_count": s.record_count}

        if method == "POST" and path == "/api/warehouse/purge":
            s = engine.warehouse_purge(root=root)
            return 200, {"record_count": s.record_count, "skipped_reason": s.skipped_reason}

        # ---- AI assistant settings (off / local / api; MCP path needs none) ---
        if method == "GET" and path == "/api/ai-config":
            return 200, engine.ai_config_get(root=root)
        if method == "POST" and path == "/api/ai-config":
            return 200, engine.ai_config_set(
                mode=body.get("mode"), endpoint=body.get("endpoint"),
                provider=body.get("provider"), model_id=body.get("model_id"), root=root)
        if method == "GET" and path == "/api/ai/local-models":
            return 200, engine.ai_local_models(root=root)

        # ---- Atlas contribution: build a bundle / revocation (NO transmission) --
        # The panel offers the returned bundle as a local download; nothing is sent
        # anywhere from here (download-only egress — there is no upload endpoint).
        if method == "POST" and path == "/api/atlas/contribution-preview":
            return 200, engine.atlas_contribution_preview(
                allow_claim_text=bool(body.get("allow_claim_text", False)), root=root)

        if method == "POST" and path == "/api/atlas/revoke":
            return 200, engine.atlas_revoke(_req(body, "contribution_id"),
                                            reason=body.get("reason"), root=root)

        # ---- manuscripts (inline review surface) ---------------------------
        if method == "GET" and path == "/api/manuscripts":
            mdir = prefs.get_manuscripts_dir(root)
            groups = _manuscript_groups(root)
            out = []
            seen = set()
            for mid, rows in groups.items():
                resolved = M.resolve_path(mdir, mid) is not None
                out.append({"manuscript_id": mid, "claim_count": len(rows),
                            "resolved": resolved})
                seen.add(mid)
            # Also surface documents that live in the bound folder but have no claims
            # yet, so a manuscript you just ADDED is selectable instead of being hidden
            # behind the one you've already worked on (the "always the stale one" trap).
            for name in M.list_manuscript_files(mdir):
                if name not in seen:
                    out.append({"manuscript_id": name, "claim_count": 0, "resolved": True})
                    seen.add(name)
            # the manuscript last worked on, so the client reopens it on reload instead
            # of snapping to the first entry (only honoured if still in the list)
            active = prefs.recall_manuscript(root)
            if active not in seen:
                active = None
            return 200, {"manuscripts_dir": mdir, "manuscripts": out, "active": active}

        m = re.fullmatch(r"/api/manuscript/(.+)", path)
        if method == "GET" and m:
            mid = m.group(1)
            mdir = prefs.get_manuscripts_dir(root)
            prefs.remember_manuscript(root, mid)   # opening it = now working on it
            rows = _manuscript_groups(root).get(mid, [])
            view = M.build_view(mid, [_row_claim(r) for r in rows], mdir)
            view["manuscripts_dir"] = mdir
            view["claim_states"] = {r.claim_id: _claim_state(r) for r in rows}
            return 200, view

        # No-terminal setup: initialise the ledger for the folder the panel was opened in,
        # so a user who launched in a fresh directory can start the review without running
        # `citevahti init` in a shell. Takes no input (uses the current root), idempotent.
        if method == "POST" and path == "/api/setup":
            from ..state import CiteVahtiStore
            store = CiteVahtiStore(root)
            created = not store.exists()
            if created:
                store.init()
            return 200, {"ok": True, "created": created,
                         "root": str(Path(root).expanduser())}

        if method == "POST" and path == "/api/manuscripts/bind":
            mdir = _req(body, "dir")
            prefs.set_manuscripts_dir(root, mdir)
            return 200, {"ok": True, "manuscripts_dir": prefs.get_manuscripts_dir(root)}

        # is Pandoc ready (without downloading)? — lets the UI warn before a first-run fetch
        if method == "GET" and path == "/api/pandoc/status":
            return 200, engine.pandoc_status()

        # one-click cite-stable export: embed [@citekey] for accepted claims into the
        # bound .md + write references.bib beside it (and a .docx if Pandoc is present).
        if method == "POST" and path == "/api/manuscripts/cite-export":
            mid = _req(body, "manuscript_id")
            p = M.resolve_path(prefs.get_manuscripts_dir(root), mid)
            if p is None:
                return 400, {"error": "manuscript_not_resolved", "code": "manuscript_not_resolved",
                             "message": "bind the manuscript's folder first so CiteVahti can "
                                        "write the cited copy beside it"}
            return 200, engine.cite_export_manuscript(
                str(p), make_docx=bool(body.get("docx", True)), root=root)

        # loopback-only folder browser: lets the user click through their filesystem
        # to pick a manuscripts folder instead of hand-typing a path (the no-terminal
        # constraint). Read-only listing of sub-directories + manuscript-file counts.
        if method == "POST" and path == "/api/fs/browse":
            return 200, _browse_dir(body.get("path"))

        # First-run hand-off: save a pasted Markdown manuscript, bind its folder, and
        # tell the user the MCP prompt to extract claims. Extraction stays chat-driven
        # (no AI in the panel) — this only writes the file and points at the next step.
        if method == "POST" and path == "/api/manuscripts/paste":
            name = _safe_md_name(_req(body, "filename"))
            content = _req(body, "content")
            mdir = prefs.get_manuscripts_dir(root) or str(Path(root) / "manuscripts")
            dest_dir = Path(mdir).expanduser()
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
            if dest.exists():
                raise HttpError(409, f"{name} already exists in the manuscripts folder",
                                code="file_exists",
                                remediation="Choose a different filename or remove the existing file.")
            dest.write_text(content, encoding="utf-8")
            prefs.set_manuscripts_dir(root, str(dest_dir))
            return 200, {"ok": True, "manuscripts_dir": str(dest_dir), "filename": name,
                         "next_prompt": f"Extract the verifiable claims from {name} and "
                                        "stage them for review."}

        # ---- find evidence: search (PubMed or the Zotero library) then link ----
        if method == "POST" and path == "/api/search":
            return 200, _search(root, _req(body, "query"),
                                body.get("source", "pubmed"), int(body.get("max_results", 15)))

        if method == "POST" and path == "/api/link":
            claim_id = _req(body, "claim_id")
            batch_id = _req(body, "batch_id")
            record_ids = body.get("record_ids")
            resolved = _resolve_missing_dois(root, batch_id, record_ids)   # backfill before linking
            rep = engine.link_candidates(claim_id, batch_id, record_ids=record_ids, root=root)
            return 200, {"linked": getattr(rep, "linked", None),
                         "skipped_duplicates": getattr(rep, "skipped_duplicates", None),
                         "total_candidates": getattr(rep, "total_candidates", None),
                         "doi_resolved": resolved}

        # ---- direct "Save to Zotero" for a search hit (preview → confirm) ------
        # Pushes a staged search record into the Zotero library as an item, WITHOUT
        # going through the claim rate→decide gate. Same write-safety invariant as
        # the claim write: preview returns a confirm_token; commit needs it. This is
        # "add this paper to my library", not the validated-evidence claim write.
        if method == "POST" and path == "/api/intake/preview":
            batch_id = _req(body, "batch_id")
            record_ids = body.get("record_ids")
            _resolve_missing_dois(root, batch_id, record_ids)   # carry the authoritative DOI
            return 200, engine.intake_push(batch_id, record_ids=record_ids,
                                           collection_key=body.get("collection_key"),
                                           dry_run=True, root=root)

        if method == "POST" and path == "/api/intake/commit":
            return 200, engine.intake_push(_req(body, "batch_id"),
                                           record_ids=body.get("record_ids"),
                                           collection_key=body.get("collection_key"),
                                           dry_run=False,
                                           confirm_token=_req(body, "confirm_token"), root=root)

        # guarded remove: unlink the wrong paper from a claim (audited, non-destructive)
        if method == "POST" and path == "/api/candidates/unlink":
            return 200, engine.unlink_candidate(_req(body, "claim_id"), _req(body, "candidate_id"), root=root)

        # ---- library maintenance: backfill DOIs / re-check Zotero membership ----
        if method == "POST" and path == "/api/candidates/resolve-dois":
            return 200, engine.backfill_candidate_dois(root=root)

        if method == "POST" and path == "/api/candidates/recheck-library":
            return 200, engine.recheck_library(root=root)

        if method == "POST" and path == "/api/candidates/scan-retractions":
            return 200, engine.scan_retractions(root=root)

        # fill candidates' reuse rights (oa_status/license) from OpenAlex — reports,
        # never decides reusability (one outbound OpenAlex call per DOI/PMID, on click).
        if method == "POST" and path == "/api/candidates/scan-licenses":
            return 200, engine.scan_licenses(root=root)

        # locate a candidate in the Zotero library so the UI can deep-link its PDF
        if method == "POST" and path == "/api/zotero/locate":
            return 200, engine.zotero_locate(doi=body.get("doi"), title=body.get("title"),
                                             pmid=body.get("pmid"), root=root)

        # the paper's own highlights + a full-text snippet from Zotero (read while rating)
        if method == "POST" and path == "/api/zotero/evidence":
            return 200, engine.zotero_evidence(doi=body.get("doi"), title=body.get("title"),
                                               pmid=body.get("pmid"), root=root)

        # deterministic lexical check: do the claim's terms appear in the candidate's
        # abstract? (shown only after the human rates — see the UI gating.)
        if method == "POST" and path == "/api/claim-check":
            store = engine._open_store(root)
            claim = store.load_claim(_req(body, "claim_id"))
            cand = next((c for c in store.load_candidates(claim.claim_id).candidates
                         if c.candidate_id == _req(body, "candidate_id")), None)
            text = (getattr(cand, "abstract", None) or "") if cand else ""
            return 200, engine.claim_lexical_check(claim.claim_text, text)

        # ---- connect (status-only; secret values never returned/logged) ----
        if method == "POST" and path == "/api/connect/zotero":
            engine.connect_zotero(_req(body, "api_key"), root=root)
            return 200, {"status": "ok", "health": agent.tools.status(root=root)}

        if method == "POST" and path == "/api/connect/pubmed":
            engine.onboard(root=root, ncbi_email=_req(body, "email"),
                           ncbi_api_key=body.get("api_key") or None)
            return 200, {"status": "ok", "health": agent.tools.status(root=root)}

        # OAuth 1.0a: start the handshake; stash the temp token secret server-side
        # (loopback only), hand the browser only the URL to authorize.
        if method == "POST" and path == "/api/connect/zotero/oauth/start":
            base = (_req(body, "callback_base")).rstrip("/")
            # Default to the loopback callback (most private — no external server in
            # the flow). A hosted callback (e.g. https://vahtian.com/citevahti/auth/
            # zotero/callback) may be set via env; that page MUST bounce the params
            # back to this loopback /oauth/zotero/callback so the key stays local.
            callback = os.environ.get("CITEVAHTI_ZOTERO_OAUTH_CALLBACK") or (base + "/oauth/zotero/callback")
            res = engine.zotero_oauth_start(callback, root=root)
            # hold the temp token secret in memory only (TTL) — never on disk
            _oauth_pending_put(res["oauth_token"], res["oauth_token_secret"])
            return 200, {"authorize_url": res["authorize_url"], "oauth_token": res["oauth_token"]}

        # ---- document write-back (revise/strike → .md; preview→commit→undo)-
        if method == "POST" and path == "/api/document/preview-edit":
            return 200, _preview_edit(root, body)

        if method == "POST" and path == "/api/document/commit-edit":
            return 200, _commit_edit(root, _req(body, "token"))

        if method == "POST" and path == "/api/document/undo-edit":
            return 200, _undo_edit(root, _req(body, "transaction_id"))

        return 404, {"error": "not_found", "code": "not_found",
                     "message": f"no route for {method} {path}", "remediation": ""}
    except Exception as e:  # noqa: BLE001 — degrade honestly with a stable shape, never 500-crash
        return _error_payload(e)


def _req(body: dict, key: str):
    if key not in body or body[key] in (None, ""):
        raise HttpError(400, f"missing required field: {key}")
    return body[key]


def _safe_md_name(raw: str) -> str:
    """A safe ``.md`` basename for a pasted manuscript — no path traversal.

    Strips any directory parts, keeps a conservative character set, and forces a
    ``.md`` suffix. Rejects names that reduce to nothing."""
    base = Path(str(raw)).name  # drops dirs and .. components
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(". ")
    if base.lower().endswith(".md"):
        base = base[:-3].rstrip(". ")
    if not base:
        raise HttpError(400, "invalid filename", code="bad_filename",
                        remediation="Use a plain name like my-draft.md.")
    return base + ".md"


# manuscript file types the browser counts/surfaces when picking a folder
_MS_SUFFIXES = (".md", ".markdown", ".txt", ".docx", ".tex")


def _browse_dir(raw_path) -> dict:
    """List sub-directories of ``raw_path`` (default: home) for the folder picker.

    Read-only and loopback-only. Returns the resolved path, its parent, and each
    sub-directory with a count of manuscript-like files inside it — so the user can
    see "the folder with 3 .md files" and bind it without typing a path. Hidden
    directories are skipped; unreadable entries degrade silently."""
    base = Path(raw_path).expanduser() if raw_path else Path.home()
    try:
        base = base.resolve()
    except OSError:
        base = Path.home()
    if not base.is_dir():
        base = Path.home()
    dirs = []
    try:
        for entry in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            try:
                n = sum(1 for f in entry.iterdir()
                        if f.is_file() and f.suffix.lower() in _MS_SUFFIXES)
            except OSError:
                n = 0
            dirs.append({"name": entry.name, "path": str(entry), "manuscript_count": n})
    except OSError:
        pass
    here = sum(1 for f in base.iterdir()
               if f.is_file() and f.suffix.lower() in _MS_SUFFIXES) if base.is_dir() else 0
    parent = str(base.parent) if base.parent != base else None
    return {"path": str(base), "parent": parent, "manuscript_count": here, "dirs": dirs}


# ---- find evidence: stage candidates from PubMed or the Zotero library ------
# PubMed uses the engine's literature_search; the Zotero library is searched
# read-only and its hits are staged through the SAME manual-intake path that other
# non-PubMed sources use, so linking + dedupe behave identically. Staging only —
# nothing is decided or written; the human still rates each candidate.
def _zotero_items_to_csv(items: list) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["title", "doi", "year", "authors"])
    for it in items or []:
        year = (it.get("date") or "")[:4]
        authors = "; ".join(
            (c.get("lastName") or c.get("name") or "").strip()
            for c in (it.get("creators") or []) if isinstance(c, dict))
        w.writerow([it.get("title") or "", it.get("DOI") or "", year, authors])
    return buf.getvalue()


def _resolve_missing_dois(root: str, batch_id: str, record_ids) -> int:
    """At link time, backfill DOIs for hits that have a PMID but no DOI, so the
    candidate (and any later Zotero write) carries the authoritative DOI. Enriches
    the staged batch in place; degrades to 0 on any error — never blocks linking."""
    try:
        store = engine._open_store(root)
        batch = store.load_intake(batch_id)
    except Exception:  # noqa: BLE001
        return 0
    want = set(record_ids) if record_ids else None
    need = [h for h in batch.hits
            if (want is None or h.record_id in want) and h.pmid and not h.doi]
    if not need:
        return 0
    resolved = engine.resolve_dois([h.pmid for h in need], root=root)
    if not resolved:
        return 0
    new_hits = [h.model_copy(update={"doi": resolved[h.pmid]})
                if (h.pmid in resolved and not h.doi) else h for h in batch.hits]
    store.save_intake(batch.model_copy(update={"hits": new_hits}))
    return sum(1 for h in need if resolved.get(h.pmid))


def _openalex_hits_to_csv(items: list) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["title", "doi", "pmid", "year", "authors"])
    for it in items or []:
        w.writerow([it.get("title") or "", it.get("doi") or "", it.get("pmid") or "",
                    it.get("year") or "", "; ".join(it.get("authors") or [])])
    return buf.getvalue()


def _search(root: str, query: str, source: str, max_results: int) -> dict:
    if source == "zotero":
        # "all" = personal + group libraries: a thesis writer's sources often
        # live in a group library, and personal-only search would miss them.
        res = engine.zot_search(query, library="all", limit=max_results)
        if not getattr(res, "ok", False):
            raise HttpError(400, f"Zotero library search unavailable ({getattr(res, 'error_code', '?')}) "
                            "— is Zotero running with the local API + Better BibTeX?")
        items = res.data or []
        if not items:
            return {"batch_id": None, "source": "zotero", "hits": []}
        rec = engine.import_results({"text": _zotero_items_to_csv(items)}, "csv",
                                    source_label=f"zotero:{query}", root=root)
    elif source == "openalex":
        items = engine.openalex_search(query, max_results, root=root)
        if not items:
            return {"batch_id": None, "source": "openalex", "hits": []}
        rec = engine.import_results({"text": _openalex_hits_to_csv(items)}, "csv",
                                    source_label=f"openalex:{query}", root=root)
    elif source == "semanticscholar":
        items = engine.semanticscholar_search(query, max_results, root=root)
        if not items:
            return {"batch_id": None, "source": "semanticscholar", "hits": []}
        rec = engine.import_results({"text": _openalex_hits_to_csv(items)}, "csv",
                                    source_label=f"s2:{query}", root=root)
    else:
        # request abstracts so the user can read them in the results before linking
        rec = engine.literature_search(query, max_results=max_results,
                                       include_abstracts=True, root=root)
    if getattr(rec, "status", "ok") not in ("ok", None):
        raise HttpError(400, f"search failed ({rec.error_code}): {rec.remediation or ''}".strip())
    hits = [{"record_id": h.record_id, "title": h.title,
             "journal": getattr(h, "journal", None), "year": getattr(h, "year", None),
             "pmid": h.pmid, "doi": h.doi, "abstract": getattr(h, "abstract", None),
             "dedupe_status": getattr(h, "dedupe_status", None)} for h in rec.hits]
    return {"batch_id": rec.batch_id, "source": source, "status": getattr(rec, "status", "ok"),
            "hits": hits}


# ---- document write-back: revise/strike a claim in the source .md -----------
# Mirrors the Zotero write gate: preview returns a token + diff, commit needs the
# token and backs up the file first, undo restores byte-for-byte. Nothing is ever
# applied to a manuscript without an explicit confirm.
def _claim_source(root: str, claim_id: str):
    """Resolve a claim's source file + text, or raise a clear HttpError."""
    store = engine._open_store(root)
    claim = store.load_claim(claim_id)
    mdir = prefs.get_manuscripts_dir(root)
    src_path = M.resolve_path(mdir, claim.manuscript_id)
    if src_path is None:
        raise HttpError(400, "manuscript source not found — bind a manuscripts folder first")
    return claim, src_path


def _preview_edit(root: str, body: dict) -> dict:
    claim_id = _req(body, "claim_id")
    kind = _req(body, "kind")
    claim, src_path = _claim_source(root, claim_id)
    replacement = body.get("replacement")
    if kind == "revise" and not replacement:
        replacement = getattr(claim, "proposed_revision", None)   # fall back to the pending rewrite
    source = src_path.read_text(encoding="utf-8")
    ed = M.compute_edit(source, {"claim_text": claim.claim_text,
                                 "manuscript_location": claim.manuscript_location},
                        kind, replacement=replacement)
    if not ed["ok"]:
        raise HttpError(400, ed["reason"])
    token = uuid.uuid4().hex
    panel = prefs.load_panel(root)
    panel.setdefault("pending_edits", {})[token] = {
        "path": str(src_path), "new_text": ed["new_text"], "claim_id": claim_id,
        "kind": kind, "replacement": replacement,
        # bind the token to the previewed contents: a commit must not overwrite a file
        # that changed since the preview (the diff was computed against THIS text).
        "src_sha": hashlib.sha256(source.encode("utf-8")).hexdigest()}
    prefs.save_panel(root, panel)
    return {"ok": True, "token": token, "kind": kind, "diff": ed["diff"],
            "path": str(src_path)}


_DEFAULT_BACKUP_RETENTION = 10


def _backup_retention_count() -> int:
    """How many backups to keep per manuscript (``CITEVAHTI_BACKUP_RETENTION_COUNT``).

    Defaults to 10. A non-integer or non-positive value falls back to the default,
    and the result is never below 1 — the newest valid backup is always kept."""
    raw = os.environ.get("CITEVAHTI_BACKUP_RETENTION_COUNT")
    if raw is None:
        return _DEFAULT_BACKUP_RETENTION
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_BACKUP_RETENTION
    return n if n >= 1 else _DEFAULT_BACKUP_RETENTION


def _prune_backups(backups_dir: Path, manuscript_name: str, keep_path: Path) -> None:
    """Keep only the N most recent backups for one manuscript; delete older ones.

    Called AFTER a new backup is successfully written. ``keep_path`` is that just-written
    backup — it is always retained regardless of clock resolution (the rule "never delete
    the newest valid backup"). Backups for a manuscript are named ``<name>.<token>.bak``;
    other manuscripts in the same folder are untouched. Best effort — a failed unlink
    never breaks the commit that triggered it."""
    keep = _backup_retention_count()
    prefix = manuscript_name + "."
    mine = [p for p in backups_dir.glob("*.bak")
            if p.name.startswith(prefix) and p.is_file()]
    if len(mine) <= keep:
        return
    # newest first; ties broken by name so the order is deterministic
    mine.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    survivors = {keep_path.resolve()}                  # the just-written backup, always
    for p in mine:
        if len(survivors) >= keep:
            break
        survivors.add(p.resolve())
    for stale in mine:
        if stale.resolve() in survivors:
            continue
        try:
            stale.unlink()
        except OSError:
            pass


def _commit_edit(root: str, token: str) -> dict:
    panel = prefs.load_panel(root)
    pending = panel.get("pending_edits", {})
    pe = pending.pop(token, None)
    if pe is None:
        raise HttpError(400, "unknown or used edit token — preview again")
    src_path = Path(pe["path"])
    # refuse to commit a stale preview: if the file changed since preview, the diff no
    # longer applies and writing new_text would clobber the intervening edit.
    if pe.get("src_sha"):
        try:
            current = src_path.read_text(encoding="utf-8")
        except OSError:
            prefs.save_panel(root, panel)
            raise HttpError(409, "the manuscript file is no longer readable — preview again")
        if hashlib.sha256(current.encode("utf-8")).hexdigest() != pe["src_sha"]:
            prefs.save_panel(root, panel)   # the token was consumed; force a fresh preview
            raise HttpError(409, "the manuscript changed since the preview", code="stale_preview")
    backups = Path(root).expanduser() / ".citevahti" / "manuscript_backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"{src_path.name}.{token}.bak"
    backup.write_bytes(src_path.read_bytes())          # back up BEFORE writing
    _prune_backups(backups, src_path.name, backup)     # keep the N most recent for this file
    src_path.write_text(pe["new_text"], encoding="utf-8")
    txn_id = "doc-" + token[:12]
    panel.setdefault("edit_txns", {})[txn_id] = {
        "path": str(src_path), "backup": str(backup), "claim_id": pe["claim_id"],
        "kind": pe["kind"]}
    prefs.save_panel(root, panel)
    # record the revision in the ledger too, so claim text and document agree
    if pe["kind"] == "revise" and pe.get("replacement"):
        try:
            engine.propose_revision(pe["claim_id"], pe["replacement"], root=root)
            engine.accept_revision(pe["claim_id"], root=root)
        except Exception:  # noqa: BLE001 — the file write already succeeded; ledger is best-effort
            pass
    return {"status": "committed", "transaction_id": txn_id, "path": str(src_path)}


def _undo_edit(root: str, txn_id: str) -> dict:
    panel = prefs.load_panel(root)
    tx = panel.get("edit_txns", {}).pop(txn_id, None)
    if tx is None:
        raise HttpError(400, "unknown document transaction")
    src_path, backup = Path(tx["path"]), Path(tx["backup"])
    if not backup.exists():
        raise HttpError(400, "backup missing — cannot undo this document edit")
    src_path.write_bytes(backup.read_bytes())
    prefs.save_panel(root, panel)
    return {"status": "undone", "path": str(src_path)}


# ---- HTTP server ------------------------------------------------------------
def _handler_factory(root: str):
    box = {"root": root}   # mutable so /api/root can switch ledger without a restart
    # Per-session CSRF token, minted once per server process and handed to the legitimate
    # loopback page at GET /api/session. State-changing requests must echo it back in the
    # X-CiteVahti-Token header. This is a POSITIVE check (must present an unguessable secret)
    # layered on top of the Origin/Host allow-list: it stays sound even if that allow-list
    # parser ever mishandles an adversarial header value. A cross-origin page cannot read the
    # token (the browser blocks reading the cross-origin /api/session response), and a
    # DNS-rebound request is already 403'd on the Host header before it can fetch it.
    csrf_token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        server_version = "CiteVahtiPanel/0.1"
        # Never hold a keep-alive socket open: a browser keeps several connections
        # alive, which on this small server would block later requests. One request
        # per connection keeps the loopback panel responsive.
        protocol_version = "HTTP/1.0"

        def log_message(self, *args):  # noqa: D401 — keep the panel quiet; no telemetry
            pass

        def _send(self, status: int, payload: dict):
            data = json.dumps(payload).encode()
            self.close_connection = True
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def _static(self) -> bool:
            name = _STATIC.get(self.path.split("?", 1)[0])
            if not name:
                return False
            f = WEB_DIR / name
            if not f.exists():
                self._send(404, {"error": "not_found", "message": f"{name} missing"})
                return True
            data = f.read_bytes()
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", _CONTENT_TYPE.get(f.suffix, "text/plain"))
            self.send_header("Content-Length", str(len(data)))
            # the panel ships as plain static files that update in place; always
            # revalidate so a refresh after an update never serves stale UI.
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            return True

        def _send_html(self, status: int, html: str):
            data = html.encode()
            self.close_connection = True
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def _oauth_callback(self):
            # Zotero redirects the browser here after the user authorizes. Finish the
            # handshake (store the key), then show a small "done" page.
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            token = (q.get("oauth_token") or [""])[0]
            verifier = (q.get("oauth_verifier") or [""])[0]
            secret = _oauth_pending_take(token)   # in-memory only; single use; TTL-expired -> None
            try:
                if not (token and verifier and secret):
                    raise HttpError(400, "this OAuth callback is stale or unknown — start again from the panel")
                engine.zotero_oauth_finish(token, secret, verifier, root=box["root"])
                msg, ok = "Zotero connected. You can close this tab and return to the panel.", True
            except Exception as e:  # noqa: BLE001 — show the reason on the page
                msg, ok = f"Could not connect Zotero: {e}", False
            self._send_html(200, "<!doctype html><meta charset=utf-8>"
                            "<title>CiteVahti · Zotero</title>"
                            "<body style='font:15px -apple-system,sans-serif;padding:40px;"
                            "background:#121022;color:#ECE7F6'>"
                            f"<h2 style='color:{'#3FB3A0' if ok else '#C8537F'}'>"
                            f"{'✓ Connected' if ok else '⚠ Not connected'}</h2><p>{esc_html(msg)}</p>"
                            "<p style='color:#9A93B0'>This window is safe to close.</p></body>")

        @staticmethod
        def _is_loopback(value: str) -> bool:
            """True if a Host/Origin header value names the loopback interface."""
            if not value:
                return False
            host = value.strip()
            if "://" in host:              # Origin: strip the scheme
                host = host.split("://", 1)[1]
            host = host.split("/", 1)[0]   # drop any path
            if host.startswith("["):       # ipv6 literal: [::1] or [::1]:port
                host = host[1:].split("]", 1)[0]
            elif host.count(":") == 1:     # host:port
                host = host.rsplit(":", 1)[0]
            return host.strip().lower() in ("localhost", "127.0.0.1", "::1")

        def _reject_bad_host(self) -> bool:
            """Reject a non-loopback Host header (defeats DNS-rebinding). 403 if rejected."""
            host = self.headers.get("Host", "")
            if host and not self._is_loopback(host):
                self._send(403, {"error": "forbidden",
                                 "message": "rejected: the panel serves the loopback interface only"})
                return True
            return False

        def _reject_unsafe_mutation(self) -> bool:
            """State-changing requests: reject a cross-origin Origin (CSRF) and require
            application/json. The JSON requirement blocks the cross-origin "simple request"
            a browser sends without a CORS preflight (text/plain / form-encoded). 403/415."""
            origin = self.headers.get("Origin")
            if origin and not self._is_loopback(origin):
                self._send(403, {"error": "forbidden",
                                 "message": "cross-origin request rejected"})
                return True
            # Positive CSRF defense: require the per-session token the page was handed at
            # /api/session (constant-time compare). Robust even if the Origin/Host parser has
            # an edge case, and it costs the legitimate client nothing — its api() helper sends
            # the header automatically. A stale token (server restarted) → reload the panel.
            token = self.headers.get("X-CiteVahti-Token", "")
            if not secrets.compare_digest(token, csrf_token):
                self._send(403, {"error": "forbidden",
                                 "message": "missing or invalid session token — reload the panel"})
                return True
            ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if ctype != "application/json":
                self._send(415, {"error": "unsupported_media_type",
                                 "message": "POST requires Content-Type: application/json"})
                return True
            return False

        def do_GET(self):
            if self._reject_bad_host():
                return
            path = self.path.split("?", 1)[0]
            # Hand the loopback page its per-session CSRF token. Reaching here means the Host
            # header already passed the loopback check, and a cross-origin page can't read this
            # response — so only the legitimate same-origin client obtains the token.
            if path == "/api/session":
                self._send(200, {"csrf_token": csrf_token})
                return
            if self.path.startswith("/oauth/zotero/callback"):
                self._oauth_callback()
            elif self.path.startswith("/api/"):
                status, payload = dispatch(box["root"], "GET", path, None)
                self._send(status, payload)
            elif not self._static():
                self._send(404, {"error": "not_found", "message": self.path})

        def do_POST(self):
            if self._reject_bad_host() or self._reject_unsafe_mutation():
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                self._send(400, {"error": "bad_json", "message": "request body is not JSON"})
                return
            path = self.path.split("?", 1)[0]
            # switching the active ledger is server state, so it lives here, not in
            # the pure dispatch(): point the box at a new root and remember it.
            if path == "/api/root":
                new = (body or {}).get("root")
                if new and prefs.has_ledger(new):
                    box["root"] = str(Path(new).expanduser().resolve())
                    prefs.remember_root(box["root"])
                    self._send(200, {"ok": True, "root": box["root"]})
                else:
                    self._send(400, {"error": "no_ledger",
                                     "message": f"no .citevahti ledger at {new!r}"})
                return
            status, payload = dispatch(box["root"], "POST", path, body)
            self._send(status, payload)

    return Handler


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def is_loopback(host: str) -> bool:
    return host in LOOPBACK_HOSTS


def make_server(root: str = ".", host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Build the loopback panel server. ``host`` defaults to ``127.0.0.1`` and is
    intended to stay there — the panel is single-user and never exposed externally."""
    return ThreadingHTTPServer((host, port), _handler_factory(root))


def serve(root: str = ".", host: str = "127.0.0.1", port: int = 8765, *,
          allow_nonloopback: bool = False) -> int:
    # Privacy is a product promise: the panel renders manuscript claims and
    # evidence and has no auth. Refuse to bind anywhere but loopback unless the
    # operator explicitly opts out.
    if not is_loopback(host) and not allow_nonloopback:
        print(f"refusing to bind {host!r}: the CiteVahti panel is loopback-only by "
              "design (single-user, no authentication). Bind 127.0.0.1, or pass "
              "--allow-nonloopback to override at your own risk.")
        return 2
    if not is_loopback(host):
        print(f"WARNING: binding non-loopback {host!r} — the panel has no auth and "
              "exposes manuscript claims/evidence to the network. You opted in.")
    prefs.remember_root(root)   # so the next launch defaults here, not an empty ledger
    httpd = make_server(root, host, port)
    bound_host, bound_port = httpd.server_address[0], httpd.server_address[1]
    print(f"CiteVahti side panel → http://{bound_host}:{bound_port}  (root={root})")
    print("Open it beside your chat client. Loopback only; Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()
    return 0


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="citevahti-panel",
        description="Serve the CiteVahti blind-decision side panel on loopback.")
    parser.add_argument("--root", default=None,
                        help="project root containing .citevahti/ "
                             "(default: $CITEVAHTI_ROOT, the cwd ledger, or the last-used root)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default 127.0.0.1; loopback-only unless overridden)")
    parser.add_argument("--port", type=int, default=8765, help="port (default 8765)")
    parser.add_argument("--allow-nonloopback", action="store_true",
                        help="permit binding a non-loopback address (no auth; exposes data — unsafe)")
    args = parser.parse_args(argv)
    root = prefs.resolve_default_root(args.root)   # avoid the empty-~/.citevahti trap
    return serve(root=root, host=args.host, port=args.port,
                 allow_nonloopback=args.allow_nonloopback)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
