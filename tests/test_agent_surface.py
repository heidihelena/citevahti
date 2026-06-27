"""The constrained agent surface: capability without power.

These tests are the safety contract. An agent that imports citevahti.agent gets a
fixed, small set of tools; it can never reach a raw Zotero write, a one-call
commit, the human's rating, the final decision, or the AI rating before the human.
"""

import json
import os
import sys
from types import SimpleNamespace

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
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore

pytestmark = pytest.mark.security   # the constrained agent surface (allow-list = capability w/o power)


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


# ---- the surface contract --------------------------------------------------
def test_surface_is_exactly_the_allow_list():
    assert set(agent.TOOLS) == set(policy.ALLOWED_AGENT_TOOLS)
    policy.assert_safe_surface(agent.TOOLS.keys())          # does not raise


def test_a_non_allowed_tool_is_rejected():
    with pytest.raises(AssertionError):
        policy.assert_safe_surface(list(agent.TOOLS) + ["zotero_write"])


def test_dangerous_verbs_are_absent():
    for forbidden in ("zotero_write", "decide", "commit", "set_human_rating",
                      "adjudicate", "delete_item", "get_credentials"):
        assert forbidden not in agent.TOOLS                 # only the safe verbs exist


# ---- token boundary: no write without a preview's token --------------------
def test_preview_returns_token_and_bogus_token_is_refused(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)
    dec = DecisionService(store).decide(claim_id, cand_id, "accept", "supports",
                                        rating_id=rec.rating_id)

    preview = agent.tools.preview_write(dec.decision_id, root=str(tmp_path))
    assert preview["approval_token"]                        # a real approval token

    # a fabricated token cannot write
    bogus = agent.tools.commit_write(dec.decision_id, "bogus-token", root=str(tmp_path))
    assert bogus["status"] != "committed"
    # the surface offers no tokenless commit path at all
    assert "commit" not in agent.TOOLS and "commit_write" in agent.TOOLS


# ---- blinding: AI rating hidden until the human rates -----------------------
def test_submit_ai_rating_does_not_echo_the_value(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rec = ClaimSupportEngine(store).support_start(claim_id, cand_id)
    out = agent.tools.submit_ai_support_rating(
        rec.rating_id, "directly_supports", confidence=0.9,
        fit={"claim_fit": 2}, root=str(tmp_path))
    assert out["recorded"] is True and out["blinded"] is True
    blob = json.dumps(out)
    assert "directly_supports" not in blob                 # value never echoed back
    # but it IS recorded on the rating
    assert store.load_support_rating(rec.rating_id).ai_rating.value == "directly_supports"


def test_get_provenance_blinds_ai_until_human_rates(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.submit_ai_rating(rec.rating_id, "does_not_support")   # AI only, no human yet
    eng.support_compare(rec.rating_id)                        # discordant (human absent)
    dec = DecisionService(store).decide(claim_id, cand_id, "needs_second_review",
                                        "raters not both in", rating_id=rec.rating_id)
    prov = agent.tools.get_provenance(dec.decision_id, root=str(tmp_path))
    assert prov["support"]["human"] is None
    assert prov["support"]["ai"] == "hidden (blinded until human rates)"
    assert "does_not_support" not in json.dumps(prov)


def test_get_provenance_shows_ai_once_human_has_rated(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.submit_ai_rating(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)
    dec = DecisionService(store).decide(claim_id, cand_id, "accept", "ok", rating_id=rec.rating_id)
    prov = agent.tools.get_provenance(dec.decision_id, root=str(tmp_path))
    assert prov["support"]["human"] == "directly_supports"
    assert prov["support"]["ai"] == "directly_supports"      # unblinded after human rated
    assert prov["claim_text"] and prov["pmid"] == "21714641"


# ---- propose_claim requires a pinned model ---------------------------------
def test_propose_claim_requires_pinned_model(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()                                             # default config: PENDING model
    out = agent.tools.propose_claim("X improves Y.", "effectiveness", root=str(tmp_path))
    assert out.get("error") == "model_not_pinned"


def test_propose_claim_records_ai_extracted(tmp_path):
    store, _claim_id, _cand_id = _setup(tmp_path)            # pinned
    out = agent.tools.propose_claim("X improves Y.", "mechanism", root=str(tmp_path))
    assert out["status"] == "proposed"
    claim = store.load_claim(out["claim_id"])
    assert claim.extracted_by == "ai" and claim.extraction_model == "claude-opus-4-8"


def test_pubmed_search_reports_degradation_details(monkeypatch):
    def fake_search(*args, **kwargs):
        return SimpleNamespace(
            batch_id="b1", status="degraded", exact_query="q", query_translation=None,
            total_count=0, result_count=0, review_required=False, warnings=[],
            error_code="pubmed_unavailable", remediation="try again later", hits=[])

    monkeypatch.setattr(agent.tools._t, "literature_search", fake_search)
    out = agent.tools.pubmed_search("q")
    assert out["status"] == "degraded"
    assert out["error_code"] == "pubmed_unavailable"
    assert out["remediation"] == "try again later"


def test_mcp_stdio_exposes_real_tool_schemas_and_calls_status(tmp_path):
    pytest.importorskip("mcp")
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    CiteVahtiStore(tmp_path).init()

    async def run():
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "citevahti.agent.mcp_server", "--root", str(tmp_path)],
            cwd=os.getcwd(),
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                by_name = {t.name: t for t in listed.tools}
                assert set(by_name) == set(policy.ALLOWED_AGENT_TOOLS)
                assert by_name["status"].inputSchema["properties"] == {}
                assert "query" in by_name["pubmed_search"].inputSchema["properties"]
                assert "decision_id" in by_name["preview_write"].inputSchema["properties"]
                assert "approval_token" in by_name["commit_write"].inputSchema["properties"]
                out = await session.call_tool("status", {})
                assert out.isError is False
                assert "write_backend" in out.content[0].text

    anyio.run(run)
