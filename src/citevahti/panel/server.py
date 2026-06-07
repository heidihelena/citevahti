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
import time
import uuid
from html import escape as esc_html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .. import agent
from .. import tools as engine
from . import manuscript as M
from . import prefs

WEB_DIR = Path(__file__).parent / "web"
_STATIC = {"/": "index.html", "/index.html": "index.html",
           "/app.js": "app.js", "/styles.css": "styles.css"}
_CONTENT_TYPE = {".html": "text/html; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8"}


# ---- blinding ---------------------------------------------------------------
def blinded_rating_view(record) -> dict:
    """Project a support rating for the panel, keeping the AI value hidden until a
    human rating exists (the same rule the engine + ``get_provenance`` enforce).

    The human may always see their own rating; the AI rating is only revealed once
    the human has committed theirs.
    """
    human = record.human_rating.value if record.human_rating else None
    ai_value = record.ai_rating.value if record.ai_rating else None
    ai_present = record.ai_rating is not None
    if human is not None:
        ai_shown = ai_value
    elif ai_present:
        ai_shown = "hidden (blinded until human rates)"
    else:
        ai_shown = None
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
    for rid in store.list_support_ratings():
        rec = store.load_support_rating(rid)
        if rec.claim_id == claim_id and rec.candidate_id == candidate_id:
            return rec
    return None


def _candidate_card(c) -> dict:
    return {
        "candidate_id": c.candidate_id, "pmid": c.pmid, "doi": c.doi,
        "title": c.title, "journal": c.journal, "year": c.year,
        "retrieval_query": c.retrieval_query, "why_found": c.why_found,
        "already_in_zotero": c.already_in_zotero, "dedupe_status": c.dedupe_status,
        "abstract": getattr(c, "abstract", None),
    }


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
    return {"state": r.state, "code": r.code.strip(),
            "candidate_count": r.candidate_count, "accepted_count": r.accepted_count}


# ---- routing (pure; unit-testable without sockets) --------------------------
class HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


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
            cand_views = []
            for c in cands:
                view = _candidate_card(c)
                rec = _find_rating_for(store, claim_id, c.candidate_id)
                view["rating"] = blinded_rating_view(rec) if rec else None
                view["evidence"] = evidence.get(c.candidate_id)
                cand_views.append(view)
            return 200, {"claim": {"claim_id": claim.claim_id, "claim_text": claim.claim_text,
                                   "claim_type": claim.claim_type,
                                   "manuscript_location": claim.manuscript_location,
                                   "extracted_by": claim.extracted_by,
                                   "proposed_revision": claim.proposed_revision},
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
                         "manuscripts_dir": prefs.get_manuscripts_dir(root)}

        if method == "GET" and path == "/api/ledgers":
            return 200, {"active": str(Path(root).expanduser()),
                         "ledgers": prefs.discover_ledgers(root)}

        # audit-chain integrity: recompute the hash chain and report whether the
        # append-only decision log has been tampered with (the trust signal).
        if method == "GET" and path == "/api/audit/verify":
            store = engine._open_store(root)
            return 200, {"intact": bool(store.audit.verify()),
                         "entries": len(store.audit.entries())}

        # ---- manuscripts (inline review surface) ---------------------------
        if method == "GET" and path == "/api/manuscripts":
            mdir = prefs.get_manuscripts_dir(root)
            groups = _manuscript_groups(root)
            out = []
            for mid, rows in groups.items():
                resolved = M.resolve_path(mdir, mid) is not None
                out.append({"manuscript_id": mid, "claim_count": len(rows),
                            "resolved": resolved})
            return 200, {"manuscripts_dir": mdir, "manuscripts": out}

        m = re.fullmatch(r"/api/manuscript/(.+)", path)
        if method == "GET" and m:
            mid = m.group(1)
            mdir = prefs.get_manuscripts_dir(root)
            rows = _manuscript_groups(root).get(mid, [])
            view = M.build_view(mid, [_row_claim(r) for r in rows], mdir)
            view["manuscripts_dir"] = mdir
            view["claim_states"] = {r.claim_id: _claim_state(r) for r in rows}
            return 200, view

        if method == "POST" and path == "/api/manuscripts/bind":
            mdir = _req(body, "dir")
            prefs.set_manuscripts_dir(root, mdir)
            return 200, {"ok": True, "manuscripts_dir": prefs.get_manuscripts_dir(root)}

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

        # ---- library maintenance: backfill DOIs / re-check Zotero membership ----
        if method == "POST" and path == "/api/candidates/resolve-dois":
            return 200, engine.backfill_candidate_dois(root=root)

        if method == "POST" and path == "/api/candidates/recheck-library":
            return 200, engine.recheck_library(root=root)

        if method == "POST" and path == "/api/candidates/scan-retractions":
            return 200, engine.scan_retractions(root=root)

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

        return 404, {"error": "not_found", "message": f"no route for {method} {path}"}
    except HttpError as e:
        return e.status, {"error": "bad_request", "message": e.message}
    except KeyError as e:
        return 400, {"error": "missing_field", "message": str(e)}
    except Exception as e:  # noqa: BLE001 — degrade honestly, never 500-crash the panel
        return 400, {"error": type(e).__name__, "message": str(e)}


def _req(body: dict, key: str):
    if key not in body or body[key] in (None, ""):
        raise HttpError(400, f"missing required field: {key}")
    return body[key]


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
        res = engine.zot_search(query, limit=max_results)
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
        rec = engine.literature_search(query, max_results=max_results, root=root)
    if getattr(rec, "status", "ok") not in ("ok", None):
        raise HttpError(400, f"search failed ({rec.error_code}): {rec.remediation or ''}".strip())
    hits = [{"record_id": h.record_id, "title": h.title,
             "journal": getattr(h, "journal", None), "year": getattr(h, "year", None),
             "pmid": h.pmid, "doi": h.doi,
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
            raise HttpError(409, "the manuscript changed since the preview — preview again "
                            "so the edit applies to the current text")
    backups = Path(root).expanduser() / ".citevahti" / "manuscript_backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"{src_path.name}.{token}.bak"
    backup.write_bytes(src_path.read_bytes())          # back up BEFORE writing
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

        def do_GET(self):
            if self.path.startswith("/oauth/zotero/callback"):
                self._oauth_callback()
            elif self.path.startswith("/api/"):
                status, payload = dispatch(box["root"], "GET", self.path.split("?", 1)[0], None)
                self._send(status, payload)
            elif not self._static():
                self._send(404, {"error": "not_found", "message": self.path})

        def do_POST(self):
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
