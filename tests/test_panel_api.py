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
from citevahti.agent import policy
from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.panel import blinded_rating_view, dispatch, make_server
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
