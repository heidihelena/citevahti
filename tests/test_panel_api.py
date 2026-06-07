"""The localhost side-panel HTTP API (ADR-0007): the blind human decision surface.

Safety contract:
  * binds to loopback (127.0.0.1) by default; never exposed externally.
  * a read endpoint never reveals the AI rating before a human rating exists.
  * the provenance endpoint respects the engine's blinding.
  * the guarded write reuses the token-gated agent wrappers (no raw Zotero write).
  * it introduces NO new agent capability (the allow-list is untouched).
  * it needs no cloud services (runs fully offline).
"""

import json
import threading

import httpx
import pytest

from citevahti import agent
from citevahti import tools as engine
from citevahti.agent import policy
from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.panel import blinded_rating_view, dispatch, make_server
from citevahti.probe.client import HttpResponse
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


def _pin(cfg):
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    cfg.ai_provenance.prompt_template_version = "v1"
    return cfg


def _setup(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(
        [ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873", title="NLST")]),
        library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return store, claim.claim_id, cand_id


# ---- loopback binding ------------------------------------------------------
def test_server_binds_loopback_by_default(tmp_path):
    srv = make_server(str(tmp_path), port=0)
    try:
        assert srv.server_address[0] == "127.0.0.1"   # never 0.0.0.0 by default
    finally:
        srv.server_close()


def test_serve_refuses_nonloopback_without_optin(tmp_path):
    from citevahti.panel.server import is_loopback, serve
    assert is_loopback("127.0.0.1") and is_loopback("::1") and is_loopback("localhost")
    assert not is_loopback("0.0.0.0") and not is_loopback("192.168.1.10")
    # returns the refusal code BEFORE binding any socket; no opt-in given
    assert serve(root=str(tmp_path), host="0.0.0.0") == 2


# ---- the panel adds no agent capability ------------------------------------
def test_panel_introduces_no_new_agent_capability():
    # the allow-list is still authoritative and unchanged
    assert set(agent.TOOLS) == set(policy.ALLOWED_AGENT_TOOLS)
    policy.assert_safe_surface(agent.TOOLS.keys())     # does not raise


# ---- blinding: AI hidden until the human rates -----------------------------
def test_rating_read_hides_ai_until_human_rates(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    root = str(tmp_path)
    started = dispatch(root, "POST", "/api/ratings/start",
                       {"claim_id": claim_id, "candidate_id": cand_id})[1]
    rid = started["rating_id"]
    # the chat/agent submits the AI rating (blind) BEFORE the human has rated
    agent.tools.submit_ai_support_rating(rid, "does_not_support", root=root)

    status, view = dispatch(root, "GET", f"/api/ratings/{rid}", None)
    assert status == 200
    assert view["human"] is None
    assert view["ai"] == "hidden (blinded until human rates)"
    assert view["ai_present"] is True
    assert "does_not_support" not in json.dumps(view)   # value never leaks

    # the human rates IN THE PANEL -> the AI value is now allowed to show
    _, after = dispatch(root, "POST", f"/api/ratings/{rid}/human",
                        {"value": "directly_supports"})
    assert after["human"] == "directly_supports"
    assert after["ai"] == "does_not_support"
    assert after["comparison_status"] == "discordant"


def test_blinded_rating_view_unit_rule(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    rec = eng.submit_ai_rating(rec.rating_id, "contradicts")
    assert blinded_rating_view(rec)["ai"] == "hidden (blinded until human rates)"
    rec = eng.support_commit_human(rec.rating_id, "contradicts")
    assert blinded_rating_view(rec)["ai"] == "contradicts"


# ---- provenance endpoint respects blinding ---------------------------------
def test_provenance_endpoint_blinds_until_human_rated(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    root = str(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.submit_ai_rating(rec.rating_id, "does_not_support")     # AI only
    eng.support_compare(rec.rating_id)
    dec = DecisionService(store).decide(claim_id, cand_id, "needs_second_review",
                                        "raters not both in", rating_id=rec.rating_id)
    status, prov = dispatch(root, "GET", f"/api/decisions/{dec.decision_id}/provenance", None)
    assert status == 200
    assert prov["support"]["human"] is None
    assert prov["support"]["ai"] == "hidden (blinded until human rates)"
    assert "does_not_support" not in json.dumps(prov)


# ---- write path: preview returns a token; bogus token cannot write ---------
def test_commit_requires_a_real_preview_token(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    root = str(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)
    dec = DecisionService(store).decide(claim_id, cand_id, "accept", "supports",
                                        rating_id=rec.rating_id)

    _, preview = dispatch(root, "POST", "/api/writes/preview", {"decision_id": dec.decision_id})
    assert preview["approval_token"]                            # a real token is issued

    _, bogus = dispatch(root, "POST", "/api/writes/commit",
                        {"decision_id": dec.decision_id, "approval_token": "bogus-token"})
    assert bogus["status"] != "committed"                       # forged token cannot write


def test_no_raw_write_route_and_missing_fields_rejected(tmp_path):
    root = str(tmp_path)
    # there is no endpoint that writes Zotero without going through preview->token
    status, _ = dispatch(root, "POST", "/api/zotero/write", {"item": {}})
    assert status == 404
    # commit without a token is a bad request, not a write
    status, body = dispatch(root, "POST", "/api/writes/commit", {"decision_id": "x"})
    assert status == 400 and "approval_token" in body["message"]


# ---- claims listing + unknown route ----------------------------------------
def test_claims_listing_offline(tmp_path):
    store, claim_id, _cand_id = _setup(tmp_path)
    status, data = dispatch(str(tmp_path), "GET", "/api/claims", None)
    assert status == 200
    assert any(c["claim_id"] == claim_id for c in data["claims"])


def test_unknown_route_is_404(tmp_path):
    status, body = dispatch(str(tmp_path), "GET", "/api/nope", None)
    assert status == 404 and body["error"] == "not_found"


# ---- evidence: abstract (pre-rating) + PICO fit (blinded until human rates) -
def _setup_with_abstract(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(
        [ProviderHit(pmid="21714641", title="NLST",
                     abstract="LDCT reduced lung-cancer mortality vs chest radiography.")]),
        library_index=StaticLibraryIndex()).literature_search(
            "ldct", question_id="q1", include_abstracts=True)
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return store, claim.claim_id, cand_id


def test_candidate_abstract_is_copied_at_link_time(tmp_path):
    store, claim_id, _ = _setup_with_abstract(tmp_path)
    cand = store.load_candidates(claim_id).candidates[0]
    assert "lung-cancer mortality" in (cand.abstract or "")


def test_card_shows_abstract_and_blinds_pico_until_human_rates(tmp_path):
    store, claim_id, cand_id = _setup_with_abstract(tmp_path)
    root = str(tmp_path)
    # the agent submits an AI rating + fit BEFORE the human — must not leak via evidence
    rid = dispatch(root, "POST", "/api/ratings/start",
                   {"claim_id": claim_id, "candidate_id": cand_id})[1]["rating_id"]
    agent.tools.submit_ai_support_rating(rid, "directly_supports",
                                         fit={"claim_fit": 2}, root=root)

    _, detail = dispatch(root, "GET", f"/api/claims/{claim_id}", None)
    cand = detail["candidates"][0]
    assert "lung-cancer mortality" in (cand["abstract"] or "")     # readable evidence pre-rating
    ev = cand["evidence"]
    assert ev["ai_support"] == "hidden"                            # AI rating blinded
    assert ev["fit"] is None                                       # no human fit yet
    assert "directly_supports" not in json.dumps(detail)          # AI value never leaks

    # the human rates WITH PICO fit -> fit + citation-fit appear (human-sourced); AI unblinds
    dispatch(root, "POST", f"/api/ratings/{rid}/human",
             {"value": "directly_supports",
              "fit": {"population_fit": 2, "outcome_fit": 2, "claim_fit": 2}})
    _, detail2 = dispatch(root, "GET", f"/api/claims/{claim_id}", None)
    ev2 = detail2["candidates"][0]["evidence"]
    assert ev2["fit"]["claim_fit"] == 2
    assert ev2["fit_total"] == 6                                   # 2 + 2 + 2 (PICO subscores)
    assert ev2["ai_support"] == "directly_supports"               # unblinded after human rated


# ---- a live loopback server, end to end, no cloud --------------------------
def test_live_server_serves_panel_and_health_offline(tmp_path):
    _setup(tmp_path)
    srv = make_server(str(tmp_path), port=0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        health = httpx.get(base + "/api/health", timeout=5)
        assert health.status_code == 200 and "connections" in health.json()
        page = httpx.get(base + "/", timeout=5)
        assert page.status_code == 200 and "CiteVahti" in page.text
        claims = httpx.get(base + "/api/claims", timeout=5)
        assert claims.status_code == 200
    finally:
        srv.shutdown()
        srv.server_close()


# ---- inline manuscript surface (ADR-0002): claims mapped onto real prose ----
def _setup_ms(tmp_path):
    """A ledger with one claim whose text appears in a bound manuscript file."""
    from citevahti.panel import prefs
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    msdir = tmp_path / "manuscripts"
    msdir.mkdir()
    body = ("# Intro\n\nBackground sentence.\n"
            "Low-dose CT screening reduces lung-cancer mortality in high-risk groups.\n"
            "A closing sentence.\n")
    (msdir / "draft.md").write_text(body, encoding="utf-8")
    ClaimService(store).add_claim(
        "Low-dose CT screening reduces lung-cancer mortality in high-risk groups.",
        "effectiveness", manuscript_id="draft.md", manuscript_location="draft.md:L4")
    prefs.set_manuscripts_dir(str(tmp_path), str(msdir))
    return store


def test_manuscript_maps_claims_onto_real_prose(tmp_path):
    _setup_ms(tmp_path)
    ms = dispatch(str(tmp_path), "GET", "/api/manuscripts", None)[1]
    assert ms["manuscripts"][0]["resolved"] is True
    view = dispatch(str(tmp_path), "GET", "/api/manuscript/draft.md", None)[1]
    assert view["mode"] == "file"
    claim_segs = [s for s in view["segments"] if s["kind"] == "claim"]
    assert len(claim_segs) == 1 and view["unmatched"] == []
    # prose around the claim is preserved as text segments (not just the claim)
    assert any(s["kind"] == "text" and "Background sentence" in s["text"] for s in view["segments"])


def test_manuscript_reconstructs_when_unbound(tmp_path):
    from citevahti.panel import prefs
    _setup_ms(tmp_path)
    prefs.set_manuscripts_dir(str(tmp_path), str(tmp_path / "nonexistent"))
    view = dispatch(str(tmp_path), "GET", "/api/manuscript/draft.md", None)[1]
    assert view["mode"] == "reconstructed"            # never blank, even with no file
    assert [s for s in view["segments"] if s["kind"] == "claim"]


def test_document_edit_preview_commit_undo_is_reversible(tmp_path):
    _setup_ms(tmp_path)
    src = tmp_path / "manuscripts" / "draft.md"
    before = src.read_text()
    claim_id = dispatch(str(tmp_path), "GET", "/api/claims", None)[1]["claims"][0]["claim_id"]
    pv = dispatch(str(tmp_path), "POST", "/api/document/preview-edit",
                  {"claim_id": claim_id, "kind": "strike"})[1]
    assert pv["ok"] and "~~" in pv["diff"]
    assert src.read_text() == before                  # preview writes nothing
    cm = dispatch(str(tmp_path), "POST", "/api/document/commit-edit", {"token": pv["token"]})[1]
    assert cm["status"] == "committed" and "~~" in src.read_text()
    ud = dispatch(str(tmp_path), "POST", "/api/document/undo-edit",
                  {"transaction_id": cm["transaction_id"]})[1]
    assert ud["status"] == "undone" and src.read_text() == before   # byte-for-byte


def test_document_revise_applies_authored_wording(tmp_path):
    # the panel can now author a revision (no chat-proposed_revision needed):
    # an explicit replacement flows straight into the .md diff.
    _setup_ms(tmp_path)
    claim_id = dispatch(str(tmp_path), "GET", "/api/claims", None)[1]["claims"][0]["claim_id"]
    pv = dispatch(str(tmp_path), "POST", "/api/document/preview-edit",
                  {"claim_id": claim_id, "kind": "revise",
                   "replacement": "Risk-stratified follow-up is recommended for incidental nodules."})[1]
    assert pv["ok"] and "Risk-stratified follow-up is recommended" in pv["diff"]


def test_commit_edit_requires_a_real_token(tmp_path):
    _setup_ms(tmp_path)
    status, payload = dispatch(str(tmp_path), "POST", "/api/document/commit-edit", {"token": "bogus"})
    assert status == 400 and "token" in payload["message"]


def test_connect_never_echoes_the_secret(tmp_path, monkeypatch):
    _setup(tmp_path)
    seen = {}

    def fake_connect(api_key, **kw):
        seen["key"] = api_key                          # the engine receives it...
        return {"connected": True, "user_id": "999"}
    monkeypatch.setattr(engine, "connect_zotero", fake_connect)
    monkeypatch.setattr(agent.tools, "status", lambda **kw: {"connections": {}, "can_write": []})
    SECRET = "zk_supersecret_value_123"
    status, payload = dispatch(str(tmp_path), "POST", "/api/connect/zotero", {"api_key": SECRET})
    assert status == 200 and seen["key"] == SECRET     # forwarded to the engine
    assert SECRET not in json.dumps(payload)           # ...but never returned to the browser


def test_ledger_discovery_lists_claim_counts(tmp_path):
    from citevahti.panel import prefs
    _setup(tmp_path)                                   # one claim
    found = prefs.discover_ledgers(str(tmp_path))
    mine = [d for d in found if d["root"] == str(tmp_path)]
    assert mine and mine[0]["claims"] >= 1


# ---- find evidence in the panel: search (PubMed + Zotero) then link ----------
def _hit(record_id, title, pmid=None, doi=None, journal=None, year=None):
    return type("H", (), {"record_id": record_id, "title": title, "pmid": pmid,
                          "doi": doi, "journal": journal, "year": year})()


def test_search_pubmed_returns_hits(tmp_path, monkeypatch):
    _setup(tmp_path)
    batch = type("B", (), {"batch_id": "b1", "status": "ok",
                           "hits": [_hit("r1", "LDCT trial", pmid="21714641", journal="NEJM", year=2011)]})()
    monkeypatch.setattr(engine, "literature_search", lambda q, **kw: batch)
    status, payload = dispatch(str(tmp_path), "POST", "/api/search", {"query": "ldct", "source": "pubmed"})
    assert status == 200 and payload["batch_id"] == "b1"
    assert payload["hits"][0] == {"record_id": "r1", "title": "LDCT trial", "journal": "NEJM",
                                  "year": 2011, "pmid": "21714641", "doi": None, "dedupe_status": None}


def test_search_zotero_routes_through_manual_intake(tmp_path, monkeypatch):
    _setup(tmp_path)
    tr = type("TR", (), {"ok": True, "error_code": None,
                         "data": [{"title": "Z paper", "DOI": "10.1/z", "date": "2019-05",
                                   "creators": [{"lastName": "Smith"}]}]})()
    seen = {}

    def fake_import(source, fmt, **kw):
        seen["csv"] = source["text"]
        seen["fmt"] = fmt
        return type("B", (), {"batch_id": "zb1", "status": "ok",
                              "hits": [_hit("zr", "Z paper", doi="10.1/z", year=2019)]})()
    monkeypatch.setattr(engine, "zot_search", lambda q, **kw: tr)
    monkeypatch.setattr(engine, "import_results", fake_import)
    status, payload = dispatch(str(tmp_path), "POST", "/api/search", {"query": "nodule", "source": "zotero"})
    assert status == 200 and payload["source"] == "zotero" and payload["hits"][0]["record_id"] == "zr"
    # the Zotero item was staged as CSV through the SAME manual-intake path
    assert seen["fmt"] == "csv" and "title,doi,year" in seen["csv"] and "Z paper" in seen["csv"]


def test_search_zotero_unavailable_is_a_clear_error(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.setattr(engine, "zot_search",
                        lambda q, **kw: type("TR", (), {"ok": False, "error_code": "unavailable", "data": None})())
    status, payload = dispatch(str(tmp_path), "POST", "/api/search", {"query": "x", "source": "zotero"})
    assert status == 400 and "Zotero" in payload["message"]


def test_link_endpoint_forwards_to_engine(tmp_path, monkeypatch):
    _setup(tmp_path)
    seen = {}

    def fake_link(claim_id, batch_id, record_ids=None, **kw):
        seen.update(claim_id=claim_id, batch_id=batch_id, record_ids=record_ids)
        return type("Rep", (), {"linked": 2, "skipped_duplicates": 0, "total_candidates": 2})()
    monkeypatch.setattr(engine, "link_candidates", fake_link)
    monkeypatch.setattr(engine, "resolve_dois", lambda *a, **k: {})   # isolate from DOI resolution
    status, payload = dispatch(str(tmp_path), "POST", "/api/link",
                               {"claim_id": "c1", "batch_id": "b1", "record_ids": ["r1", "r2"]})
    assert status == 200 and payload["linked"] == 2
    assert seen == {"claim_id": "c1", "batch_id": "b1", "record_ids": ["r1", "r2"]}


def test_resolve_dois_returns_only_present_dois():
    class P:
        def fetch_records(self, pmids, include_abstracts=False):
            return [type("H", (), {"pmid": "1", "doi": "10.1/a"})(),
                    type("H", (), {"pmid": "2", "doi": None})()]
    assert engine.resolve_dois(["1", "2", "3"], provider=P()) == {"1": "10.1/a"}
    assert engine.resolve_dois([], provider=P()) == {}


def test_link_backfills_missing_doi_from_pmid(tmp_path, monkeypatch):
    # a candidate with a PMID but no DOI gets the authoritative DOI resolved AT LINK
    # TIME, so the candidate (and any later Zotero write) carries it.
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("LDCT reduces mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider([ProviderHit(pmid="999", doi=None, title="No-DOI paper")]),
                          library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    monkeypatch.setattr(engine, "resolve_dois", lambda pmids, **kw: {"999": "10.9/resolved"})
    rec_id = store.load_intake(batch.batch_id).hits[0].record_id
    status, payload = dispatch(str(tmp_path), "POST", "/api/link",
                               {"claim_id": claim.claim_id, "batch_id": batch.batch_id, "record_ids": [rec_id]})
    assert status == 200 and payload["doi_resolved"] == 1
    cand = store.load_candidates(claim.claim_id).candidates[0]
    assert cand.doi == "10.9/resolved"


def _setup_nodoi_candidate(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("LDCT reduces mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider([ProviderHit(pmid="999", doi=None, title="No-DOI paper")]),
                          library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    return store, claim.claim_id


def test_backfill_candidate_dois_updates_existing(tmp_path, monkeypatch):
    store, claim_id = _setup_nodoi_candidate(tmp_path)
    monkeypatch.setattr(engine, "resolve_dois", lambda pmids, **kw: {"999": "10.9/x"})
    out = engine.backfill_candidate_dois(root=str(tmp_path))
    assert out["resolved"] == 1
    assert store.load_candidates(claim_id).candidates[0].doi == "10.9/x"


def test_recheck_library_flags_candidates_now_present(tmp_path):
    store, claim_id = _setup_nodoi_candidate(tmp_path)

    class _Idx:
        def contains(self, pmid, doi):
            return True
    out = engine.recheck_library(root=str(tmp_path), index=_Idx())
    assert out["flagged"] == 1 and out["checked"] >= 1
    assert store.load_candidates(claim_id).candidates[0].already_in_zotero is True


def test_add_claim_endpoint_creates_a_claim(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    status, payload = dispatch(str(tmp_path), "POST", "/api/claims",
                               {"claim_text": "Screening reduces mortality.", "claim_type": "effectiveness",
                                "manuscript_id": "draft.md", "manuscript_location": "draft.md"})
    assert status == 200 and payload["claim_id"]
    claims = dispatch(str(tmp_path), "GET", "/api/claims", None)[1]
    assert claims["total"] == 1 and claims["claims"][0]["claim_text"] == "Screening reduces mortality."


def test_claim_history_lists_decisions(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    r = dispatch(str(tmp_path), "POST", "/api/ratings/start",
                 {"claim_id": claim_id, "candidate_id": cand_id})[1]
    dispatch(str(tmp_path), "POST", f"/api/ratings/{r['rating_id']}/human", {"value": "directly_supports"})
    dispatch(str(tmp_path), "POST", "/api/decisions",
             {"claim_id": claim_id, "candidate_id": cand_id, "final_decision": "accept",
              "decision_reason": "matches the cited source", "rating_id": r["rating_id"]})
    status, payload = dispatch(str(tmp_path), "GET", f"/api/claims/{claim_id}/history", None)
    assert status == 200 and len(payload["decisions"]) == 1
    d = payload["decisions"][0]
    assert d["final_decision"] == "accept" and d["reason"] == "matches the cited source"
    assert d["decided_by"] == "human" and d["at"]               # who + when, for the audit trail
    assert payload["transactions"] == []                        # no Zotero write in this offline test


def test_claim_lexical_check_engine():
    # claim terms present in the text -> terms_present; reuses content-token overlap
    yes = engine.claim_lexical_check("Low-dose CT screening reduces lung-cancer mortality",
                                     "Screening with low-dose CT reduced lung-cancer mortality versus radiography.")
    assert yes["available"] and yes["status"] == "terms_present" and yes["coverage"] >= 0.5
    no = engine.claim_lexical_check("Prehabilitation improves surgical readiness",
                                    "This paper concerns coronary artery calcium scoring.")
    assert no["status"] == "terms_missing" and "prehabilitation" in no["missing"]
    assert engine.claim_lexical_check("anything", "") == {"available": False}


def test_claim_check_endpoint_uses_candidate_abstract(tmp_path, monkeypatch):
    store, claim_id, cand_id = _setup(tmp_path)
    # give the candidate an abstract that lexically covers the seeded claim
    cc = store.load_candidates(claim_id)
    cc.candidates[0] = cc.candidates[0].model_copy(
        update={"abstract": "LDCT reduces lung-cancer mortality in the trial."})
    store.save_candidates(cc)
    status, payload = dispatch(str(tmp_path), "POST", "/api/claim-check",
                               {"claim_id": claim_id, "candidate_id": cand_id})
    assert status == 200 and payload["available"] is True and "coverage" in payload


def test_audit_verify_reports_intact_chain(tmp_path):
    _setup(tmp_path)                                       # init + claim + intake -> audit entries
    status, payload = dispatch(str(tmp_path), "GET", "/api/audit/verify", None)
    assert status == 200 and payload["intact"] is True and payload["entries"] >= 1


def test_audit_verify_detects_tampering(tmp_path):
    _setup(tmp_path)
    # retroactively edit the first audit entry's payload but leave its hash —
    # the recomputed hash no longer matches, so the chain reports broken.
    log = tmp_path / ".citevahti" / "audit_log.jsonl"
    lines = log.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["payload"] = {"tampered": True}
    lines[0] = json.dumps(rec)
    log.write_text("\n".join(lines) + "\n")
    status, payload = dispatch(str(tmp_path), "GET", "/api/audit/verify", None)
    assert status == 200 and payload["intact"] is False    # the badge would show ⚠ tampered


def test_crossref_title_match_is_strict():
    from citevahti.crossref import CrossrefClient

    class _H:
        def __init__(self, items):
            self.items = items

        def get(self, url, params=None, headers=None):
            return HttpResponse(200, json.dumps({"message": {"items": self.items}}))

    # near-exact title → accepted
    ok = CrossrefClient(http=_H([{"DOI": "10.1/x",
                                  "title": ["Low dose CT screening reduces lung cancer mortality"]}]))
    assert ok.doi_for_title("Low-dose CT screening reduces lung-cancer mortality") == "10.1/x"
    # unrelated title → rejected (a wrong DOI is worse than none)
    no = CrossrefClient(http=_H([{"DOI": "10.2/y", "title": ["An unrelated paper about feline behaviour"]}]))
    assert no.doi_for_title("Low-dose CT screening reduces lung-cancer mortality") is None


def test_backfill_uses_crossref_for_identifierless_candidates(tmp_path, monkeypatch):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("X", "effectiveness")
    batch = engine.import_results({"text": "title\nA manual reference with no IDs\n"}, "csv", root=str(tmp_path))
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    monkeypatch.setattr(engine, "resolve_dois", lambda *a, **k: {})        # no PMID path
    monkeypatch.setattr(engine, "resolve_dois_by_title",
                        lambda titles, **k: {"A manual reference with no IDs": "10.7/title"})
    out = engine.backfill_candidate_dois(root=str(tmp_path))
    assert out["by_title"] == 1 and out["by_pmid"] == 0
    assert store.load_candidates(claim.claim_id).candidates[0].doi == "10.7/title"


def test_openalex_client_search_and_retraction():
    from citevahti.openalex import OpenAlexClient

    class _H:
        def get(self, url, params=None, headers=None):
            if url.endswith("/works"):
                return HttpResponse(200, json.dumps({"results": [{
                    "title": "A trial", "doi": "https://doi.org/10.1/x",
                    "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/123"},
                    "publication_year": 2020,
                    "primary_location": {"source": {"display_name": "NEJM"}},
                    "authorships": [{"author": {"display_name": "A B"}}],
                    "is_retracted": False}]}))
            return HttpResponse(200, json.dumps({"is_retracted": True}))
    c = OpenAlexClient(http=_H())
    hit = c.search("lung")[0]
    assert hit["doi"] == "10.1/x" and hit["pmid"] == "123" and hit["journal"] == "NEJM"
    assert hit["is_retracted"] is False
    assert c.is_retracted(doi="10.1/y") is True          # path-based DOI lookup


def test_scan_retractions_flags_candidate(tmp_path):
    store, claim_id, _cand = _setup(tmp_path)            # candidate has a real PMID+DOI

    class _C:
        def is_retracted(self, doi=None, pmid=None):
            return True
    out = engine.scan_retractions(root=str(tmp_path), client=_C())
    assert out["flagged"] == 1 and out["checked"] >= 1
    assert store.load_candidates(claim_id).candidates[0].retracted is True


def test_search_openalex_routes_through_manual_intake(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.setattr(engine, "openalex_search",
                        lambda q, n, **kw: [{"title": "OA paper", "doi": "10.5/oa",
                                             "pmid": "55", "year": 2021, "authors": ["X Y"]}])
    seen = {}

    def fake_import(source, fmt, **kw):
        seen["csv"] = source["text"]
        return type("B", (), {"batch_id": "ob", "status": "ok",
                              "hits": [_hit("or1", "OA paper", pmid="55", doi="10.5/oa")]})()
    monkeypatch.setattr(engine, "import_results", fake_import)
    status, payload = dispatch(str(tmp_path), "POST", "/api/search", {"query": "x", "source": "openalex"})
    assert status == 200 and payload["source"] == "openalex" and payload["hits"][0]["record_id"] == "or1"
    assert "title,doi,pmid" in seen["csv"] and "OA paper" in seen["csv"]


def test_semanticscholar_client_normalizes_hits():
    from citevahti.semscholar import SemanticScholarClient

    class _H:
        def get(self, url, params=None, headers=None):
            return HttpResponse(200, json.dumps({"data": [{
                "title": "A trial", "year": 2018, "venue": "Lancet",
                "externalIds": {"DOI": "10.3/s2", "PubMed": 777},
                "authors": [{"name": "C D"}]}]}))
    hit = SemanticScholarClient(http=_H()).search("lung")[0]
    assert hit == {"title": "A trial", "doi": "10.3/s2", "pmid": "777",
                   "year": 2018, "journal": "Lancet", "authors": ["C D"]}


def test_search_semanticscholar_routes_through_manual_intake(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.setattr(engine, "semanticscholar_search",
                        lambda q, n, **kw: [{"title": "S2 paper", "doi": "10.4/s", "pmid": "88",
                                             "year": 2019, "authors": ["E F"]}])
    monkeypatch.setattr(engine, "import_results",
                        lambda source, fmt, **kw: type("B", (), {"batch_id": "s2b", "status": "ok",
                                                                 "hits": [_hit("s2r", "S2 paper", pmid="88", doi="10.4/s")]})())
    status, payload = dispatch(str(tmp_path), "POST", "/api/search", {"query": "x", "source": "semanticscholar"})
    assert status == 200 and payload["source"] == "semanticscholar" and payload["hits"][0]["record_id"] == "s2r"


def test_zotero_evidence_returns_highlights_and_fulltext():
    class _Z:
        def zot_search(self, q, limit=None):
            return type("R", (), {"ok": True, "data": [{"key": "K1", "DOI": "10.1/x"}]})()

        def zot_annotations(self, ref):
            return type("R", (), {"ok": True, "data": [
                {"text": "key finding", "comment": "note", "page_label": "4"}]})()

        def zot_fulltext(self, ref):
            return type("R", (), {"ok": True, "data": {"content": "indexed full text here"}})()
    out = engine.zotero_evidence(doi="10.1/x", zotero=_Z())
    assert out["found"] is True and out["item_key"] == "K1"
    assert out["annotations"] == [{"text": "key finding", "comment": "note", "page": "4"}]
    assert out["fulltext"] == "indexed full text here"


def test_zotero_evidence_endpoint_forwards(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.setattr(engine, "zotero_evidence",
                        lambda **kw: {"found": True, "annotations": [], "fulltext": ""})
    assert dispatch(str(tmp_path), "POST", "/api/zotero/evidence", {"doi": "10.1/x"}) \
        == (200, {"found": True, "annotations": [], "fulltext": ""})


def test_zotero_locate_matches_by_doi(tmp_path):
    class _Z:
        def zot_search(self, query, limit=None):
            return type("TR", (), {"ok": True, "data": [{"key": "ABC123", "DOI": "10.1/x"}]})()
    out = engine.zotero_locate(doi="10.1/x", zotero=_Z())
    assert out["found"] is True and out["key"] == "ABC123"


def test_retraction_and_locate_endpoints_forward(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.setattr(engine, "scan_retractions", lambda **kw: {"flagged": 1, "checked": 3})
    monkeypatch.setattr(engine, "zotero_locate", lambda **kw: {"found": True, "key": "K1"})
    assert dispatch(str(tmp_path), "POST", "/api/candidates/scan-retractions", {}) == (200, {"flagged": 1, "checked": 3})
    assert dispatch(str(tmp_path), "POST", "/api/zotero/locate", {"doi": "10.1/x"}) == (200, {"found": True, "key": "K1"})


def test_maintenance_endpoints_forward(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.setattr(engine, "backfill_candidate_dois", lambda **kw: {"resolved": 2})
    monkeypatch.setattr(engine, "recheck_library", lambda **kw: {"flagged": 3, "checked": 5})
    assert dispatch(str(tmp_path), "POST", "/api/candidates/resolve-dois", {}) == (200, {"resolved": 2})
    assert dispatch(str(tmp_path), "POST", "/api/candidates/recheck-library", {}) == (200, {"flagged": 3, "checked": 5})


# ---- Zotero OAuth connect (ADR-0005): the panel wiring ----------------------
def test_oauth_start_stashes_token_serverside_and_returns_only_the_url(tmp_path, monkeypatch):
    from citevahti.panel import prefs
    _setup(tmp_path)
    monkeypatch.setattr(engine, "zotero_oauth_start", lambda callback, **kw: {
        "oauth_token": "tmptok", "oauth_token_secret": "tmpsecret",
        "authorize_url": "https://www.zotero.org/oauth/authorize?oauth_token=tmptok"})
    status, payload = dispatch(str(tmp_path), "POST", "/api/connect/zotero/oauth/start",
                               {"callback_base": "http://127.0.0.1:8765"})
    assert status == 200 and payload["authorize_url"].endswith("oauth_token=tmptok")
    assert "tmpsecret" not in json.dumps(payload)                     # secret never goes to the browser
    assert prefs.load_panel(str(tmp_path))["oauth_pending"]["tmptok"] == "tmpsecret"


def test_oauth_start_unconfigured_is_a_clear_error(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.delenv("CITEVAHTI_ZOTERO_OAUTH_CLIENT_KEY", raising=False)
    monkeypatch.delenv("CITEVAHTI_ZOTERO_OAUTH_CLIENT_SECRET", raising=False)
    status, payload = dispatch(str(tmp_path), "POST", "/api/connect/zotero/oauth/start",
                               {"callback_base": "http://127.0.0.1:8765"})
    assert status == 400 and "oauth/apps" in payload["message"]       # tells the user how to set it up


def test_oauth_callback_finishes_handshake_and_clears_pending(tmp_path, monkeypatch):
    from citevahti.panel import prefs
    _setup(tmp_path)
    panel = prefs.load_panel(str(tmp_path))
    panel["oauth_pending"] = {"tmptok": "tmpsecret"}
    prefs.save_panel(str(tmp_path), panel)
    seen = {}

    def fake_finish(token, secret, verifier, **kw):
        seen.update(token=token, secret=secret, verifier=verifier)
        return {"connected": True, "user_id": "1"}
    monkeypatch.setattr(engine, "zotero_oauth_finish", fake_finish)

    srv = make_server(str(tmp_path), port=0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        r = httpx.get(base + "/oauth/zotero/callback?oauth_token=tmptok&oauth_verifier=verif", timeout=5)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert "Connected" in r.text
        assert seen == {"token": "tmptok", "secret": "tmpsecret", "verifier": "verif"}
        assert not (prefs.load_panel(str(tmp_path)).get("oauth_pending") or {})   # used token cleared
    finally:
        srv.shutdown()
        srv.server_close()
