"""A claim citing several sources is not decided by one accept.

Support is a property of a (claim, candidate) pair, not of the claim. Accepting the
source in front of you says nothing about the papers cited alongside it: they hold no
human support rating and no decision. The report used to read the first accept as the
whole claim's verdict — the claim turned green, left the pending queue, and its co-cited
sources were silently never judged (field ledger 2026-07-28: 30 claims, 61 candidates,
31 of them never rated or decided while the reviewer believed they had accepted them
together).

These tests pin the rule end to end: the report state, the per-claim counts, the panel's
view of the claim, and the triage line that names what is left.
"""

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.panel import server as panel
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.report import ClaimReportService
from citevahti.risk.triage import triage
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


def _claim_citing_three(store):
    """One claim with THREE linked candidates — the co-citation shape that leaked."""
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    hits = [ProviderHit(pmid=str(i), doi=f"10.1/{i}", title=f"Paper {i}") for i in (1, 2, 3)]
    batch = IntakeService(store, provider=_Provider(hits),
                          library_index=StaticLibraryIndex()).literature_search("q", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cands = [c.candidate_id for c in store.load_candidates(claim.claim_id).candidates]
    assert len(cands) == 3
    return claim.claim_id, cands


def _accept(store, claim_id, cand_id, value="directly_supports", decision="accept"):
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, value)
    eng.support_compare(rec.rating_id)
    return DecisionService(store).decide(claim_id, cand_id, decision, "ok", rating_id=rec.rating_id)


def _row(store, claim_id):
    rep = ClaimReportService(store).report()
    return next(r for r in rep.rows if r.claim_id == claim_id)


# ---- the regression -------------------------------------------------------
def test_one_accept_does_not_decide_a_claim_citing_three_sources(tmp_path):
    store = _store(tmp_path)
    claim_id, cands = _claim_citing_three(store)
    _accept(store, claim_id, cands[0])

    row = _row(store, claim_id)
    assert row.candidate_count == 3
    assert row.decided_count == 1                  # one pair judged...
    assert row.accepted_count == 1
    assert row.state != "accepted"                 # ...so the CLAIM is not accepted
    assert row.state == "needs_support" and row.code == "o "
    # and the two co-cited sources carry no human rating and no decision — the accept
    # was never fanned out over them, and nothing invented a value on their behalf
    untouched = [e for e in row.evidence if e.candidate_id in cands[1:]]
    assert len(untouched) == 2
    assert all(e.final_decision is None and e.human_support is None and e.support_status is None
               for e in untouched)


def test_claim_is_accepted_only_once_every_cited_source_is_judged(tmp_path):
    store = _store(tmp_path)
    claim_id, cands = _claim_citing_three(store)
    _accept(store, claim_id, cands[0])
    _accept(store, claim_id, cands[1], value="does_not_support", decision="reject")
    assert _row(store, claim_id).state == "needs_support"      # one still unjudged

    _accept(store, claim_id, cands[2], value="partially_supports",
            decision="accepted_with_caution")
    row = _row(store, claim_id)
    assert row.state == "accepted" and row.decided_count == 3 and row.accepted_count == 2


def test_a_single_candidate_claim_is_unchanged(tmp_path):
    """The fix must not make the ordinary one-source claim harder to finish."""
    store = _store(tmp_path)
    claim = ClaimService(store).add_claim("One-source claim.", "effectiveness")
    batch = IntakeService(store, provider=_Provider([ProviderHit(pmid="9", doi="10.1/9", title="P")]),
                          library_index=StaticLibraryIndex()).literature_search("q", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    _accept(store, claim.claim_id, cand)
    row = _row(store, claim.claim_id)
    assert row.state == "accepted" and row.decided_count == row.candidate_count == 1


def test_triage_names_the_sources_left_instead_of_no_citation_yet(tmp_path):
    store = _store(tmp_path)
    claim_id, cands = _claim_citing_three(store)
    _accept(store, claim_id, cands[0])
    rep = ClaimReportService(store).report()
    item = next(i for i in triage(rep).items if i.claim_id == claim_id)
    assert "2 of this claim's 3 cited sources have no judgement yet." == item.reason
    assert "per source" in item.action


# ---- the panel sees the same thing ----------------------------------------
def test_panel_claim_view_shows_the_unjudged_sources(tmp_path):
    store = _store(tmp_path)
    claim_id, cands = _claim_citing_three(store)
    _accept(store, claim_id, cands[0])
    root = str(tmp_path)

    status, out = panel.dispatch(root, "GET", f"/api/claims/{claim_id}", None)
    assert status == 200
    views = {c["candidate_id"]: c for c in out["candidates"]}
    assert len(views) == 3
    assert views[cands[0]]["step"]["phase"] == "write"          # decided; awaits the write
    # the co-cited sources are still at the very first step: they need a human rating
    for cid in cands[1:]:
        assert views[cid]["step"]["phase"] == "rate"
        assert views[cid]["evidence"]["final_decision"] is None
        assert views[cid]["rating"] is None


def test_panel_claim_state_is_not_green_until_every_source_is_judged(tmp_path):
    store = _store(tmp_path)
    claim_id, cands = _claim_citing_three(store)
    _accept(store, claim_id, cands[0])
    rep = ClaimReportService(store).report()
    row = next(r for r in rep.rows if r.claim_id == claim_id)

    st = panel._claim_state(row)
    assert st["state"] == "needs_support"           # the manuscript span stays pending
    assert st["decided_count"] == 1 and st["candidate_count"] == 3
