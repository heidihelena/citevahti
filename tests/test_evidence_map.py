"""The Atlas evidence-map graph (tools.evidence_map + GET /api/evidence-map).

Read-only claim<->evidence graph: nodes = claims + deduplicated papers, edges =
(claim, candidate) pairs carrying the human/blinded-AI support + verdict + flags.
Reuses the ClaimReportService aggregation, so the blinding rule (AI hidden until
the human rates) and the retraction flag are asserted here as they surface on the map.
"""

from citevahti import tools as engine
from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.panel import dispatch
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


def _store(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    cfg = s.load_config()
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    cfg.ai_provenance.prompt_template_version = "v1"
    s.save_config(cfg)
    return s


def _claim_with_candidate(store, text, pmid, doi="", title="P"):
    claim = ClaimService(store).add_claim(text, "effectiveness")
    batch = IntakeService(store, provider=_Provider([ProviderHit(pmid=pmid, doi=doi, title=title)]),
                          library_index=StaticLibraryIndex()).literature_search("q", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return claim.claim_id, cand_id


def _accept(store, claim_id, cand_id, human="directly_supports"):
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, human)
    eng.support_compare(rec.rating_id)
    DecisionService(store).decide(claim_id, cand_id, "accept", "ok", rating_id=rec.rating_id)
    return rec.rating_id


# ---- structure -------------------------------------------------------------
def test_nodes_edges_and_verdict_for_accepted_claim(tmp_path):
    store = _store(tmp_path)
    cid, kid = _claim_with_candidate(store, "LDCT reduces mortality.", pmid="1", doi="10.1/a")
    _accept(store, cid, kid)

    g = engine.evidence_map(root=str(tmp_path))
    assert g["counts"] == {"claims": 1, "papers": 1, "links": 1}
    assert g["claims"][0]["id"] == cid and g["claims"][0]["code"] == "oo"
    paper = g["papers"][0]
    assert paper["id"] == "pmid:1" and paper["retracted"] is False
    edge = g["edges"][0]
    assert edge["claim_id"] == cid and edge["paper_id"] == "pmid:1"
    assert edge["decision"] == "accept" and edge["final_decision"] == "accept"
    assert edge["human_support"] == "directly_supports"


def test_claim_with_no_candidates_is_an_isolated_node(tmp_path):
    store = _store(tmp_path)
    claim = ClaimService(store).add_claim("An unsupported assertion.", "background")
    g = engine.evidence_map(root=str(tmp_path))
    assert [c["id"] for c in g["claims"]] == [claim.claim_id]
    assert g["papers"] == [] and g["edges"] == []


def test_shared_paper_is_one_node_with_two_edges(tmp_path):
    """A paper cited for two claims (same PMID) dedupes to a single node."""
    store = _store(tmp_path)
    c1, k1 = _claim_with_candidate(store, "Claim one.", pmid="21714641", doi="10.1/x")
    c2, k2 = _claim_with_candidate(store, "Claim two.", pmid="21714641", doi="10.1/x")
    _accept(store, c1, k1)
    _accept(store, c2, k2)

    g = engine.evidence_map(root=str(tmp_path))
    assert g["counts"]["claims"] == 2 and g["counts"]["papers"] == 1
    assert g["counts"]["links"] == 2
    pids = {e["paper_id"] for e in g["edges"]}
    assert pids == {"pmid:21714641"}


def test_unrated_link_blinds_the_ai_value(tmp_path):
    """AI submitted, human hasn't rated → edge is unrated and the AI stays hidden."""
    store = _store(tmp_path)
    cid, kid = _claim_with_candidate(store, "Pending claim.", pmid="7")
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(cid, kid)
    eng.submit_ai_rating(rec.rating_id, "directly_supports")   # AI only, human not yet

    edge = engine.evidence_map(root=str(tmp_path))["edges"][0]
    assert edge["decision"] == "unrated" and edge["final_decision"] is None
    assert edge["human_support"] is None and edge["ai_support"] == "hidden"

    # once the human rates + decides, the AI value is revealed
    eng.support_commit_human(rec.rating_id, "directly_supports")   # concordant with the AI
    eng.support_compare(rec.rating_id)
    DecisionService(store).decide(cid, kid, "accept", "ok", rating_id=rec.rating_id)
    edge2 = engine.evidence_map(root=str(tmp_path))["edges"][0]
    assert edge2["ai_support"] == "directly_supports" and edge2["decision"] == "accept"


def test_retracted_paper_is_flagged_independent_of_rating(tmp_path):
    store = _store(tmp_path)
    cid, kid = _claim_with_candidate(store, "Cites a retracted paper.", pmid="9")
    cc = store.load_candidates(cid)
    cc.candidates[0].retracted = True
    store.save_candidates(cc)
    # deliberately do NOT rate it — retraction is a fact, not a judgement
    g = engine.evidence_map(root=str(tmp_path))
    assert g["papers"][0]["retracted"] is True
    assert g["edges"][0]["decision"] == "unrated"


# ---- endpoint --------------------------------------------------------------
def test_endpoint_returns_the_graph(tmp_path):
    store = _store(tmp_path)
    cid, kid = _claim_with_candidate(store, "LDCT reduces mortality.", pmid="1")
    _accept(store, cid, kid)
    status, payload = dispatch(str(tmp_path), "GET", "/api/evidence-map", None)
    assert status == 200
    assert payload["counts"]["links"] == 1 and payload["edges"][0]["decision"] == "accept"
    assert "generated_at" in payload
