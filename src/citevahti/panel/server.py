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

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .. import agent
from .. import tools as engine

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


# ---- HTTP server ------------------------------------------------------------
def _handler_factory(root: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CiteVahtiPanel/0.1"

        def log_message(self, *args):  # noqa: D401 — keep the panel quiet; no telemetry
            pass

        def _send(self, status: int, payload: dict):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
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
            self.send_response(200)
            self.send_header("Content-Type", _CONTENT_TYPE.get(f.suffix, "text/plain"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return True

        def do_GET(self):
            if self.path.startswith("/api/"):
                status, payload = dispatch(root, "GET", self.path.split("?", 1)[0], None)
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
            status, payload = dispatch(root, "POST", self.path.split("?", 1)[0], body)
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
    parser.add_argument("--root", default=".", help="project root containing .citevahti/")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default 127.0.0.1; loopback-only unless overridden)")
    parser.add_argument("--port", type=int, default=8765, help="port (default 8765)")
    parser.add_argument("--allow-nonloopback", action="store_true",
                        help="permit binding a non-loopback address (no auth; exposes data — unsafe)")
    args = parser.parse_args(argv)
    return serve(root=args.root, host=args.host, port=args.port,
                 allow_nonloopback=args.allow_nonloopback)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
