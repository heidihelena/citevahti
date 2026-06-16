"""The panel "what's next" wizard endpoints (PR 2): /api/next, /api/report, and the
per-candidate `step` on /api/claims/<id>. These feed the guided banner so a user who
never opens a terminal is told the one next thing to do — without any surface
re-deriving the workflow phase (that lives in citevahti.workflow).
"""

from citevahti.claims import CandidateService, ClaimService, ClaimSupportEngine, DecisionService
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


def _pin(cfg):
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    cfg.ai_provenance.prompt_template_version = "v1"
    return cfg


def _seed_claim(tmp_path):
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


def test_next_on_empty_ledger_points_to_a_manuscript(tmp_path):
    CiteVahtiStore(str(tmp_path)).init()
    status, body = dispatch(str(tmp_path), "GET", "/api/next", None)
    assert status == 200
    assert body["next"]["kind"] == "add_claims"
    assert body["claims_total"] == 0


def test_next_with_a_pending_claim_routes_to_rating(tmp_path):
    _seed_claim(tmp_path)
    status, body = dispatch(str(tmp_path), "GET", "/api/next", None)
    assert status == 200
    assert body["next"]["kind"] == "rate"
    assert body["next"]["claim_id"]                       # a concrete claim to open
    assert "zotero_not_write_ready" in body["blockers"]   # soft: rating works without it


def test_claim_view_carries_the_server_computed_step(tmp_path):
    # a freshly-linked candidate, no human rating yet -> the panel renders "rate"
    _, claim_id, _ = _seed_claim(tmp_path)
    status, body = dispatch(str(tmp_path), "GET", f"/api/claims/{claim_id}", None)
    assert status == 200
    step = body["candidates"][0]["step"]
    assert step["phase"] == "rate"
    assert step["reveal_ready"] is False                  # AI stays blinded until the human rates
    assert step["allowed_verdicts"] == []                 # no verdict keys before a rating


def test_context_exposes_the_single_vocabulary(tmp_path):
    CiteVahtiStore(str(tmp_path)).init()
    status, body = dispatch(str(tmp_path), "GET", "/api/context", None)
    assert status == 200
    decisions = {v["decision"] for v in body["vocabulary"]["verdicts"]}
    assert decisions == {"accept", "accepted_with_caution", "needs_second_review", "reject"}


def test_report_endpoint_is_timestamped_and_audit_anchored(tmp_path):
    # the report is the "you did this work, in this order" artifact: a generation
    # timestamp + the hash-chained audit head, surfaced for the panel's Report button.
    _seed_claim(tmp_path)
    status, body = dispatch(str(tmp_path), "GET", "/api/report", None)
    assert status == 200
    assert body["total"] == 1
    assert "# " in body["markdown"]                       # a real Markdown document
    assert body["generated_at"]                           # timestamped
    assert body["audit_intact"] is True                   # chain verified at generation
    assert body["audit_entries"] and body["audit_head"]   # anchored to the audit head
    assert "Integrity:" in body["markdown"]               # the proof line is in the document
