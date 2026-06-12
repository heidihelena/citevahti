"""The [u] untestable state: a claim citing a non-indexed source (book, chapter,
grey literature) must not masquerade as a failing claim (persona review: the
qualitative researcher whose good monograph citation showed as 'needs support').
"""

import pytest

from citevahti.claims import (CandidateService, ClaimService, ClaimSupportEngine,
                              DecisionService)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.report import ClaimReportService, render_markdown, render_test_report
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


def _store(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    s.save_config(_pin(s.load_config()))
    return s


def _report_row(store, claim_id):
    rep = ClaimReportService(store).report()
    return rep, next(r for r in rep.rows if r.claim_id == claim_id)


def test_marked_claim_reports_untestable_not_needs_support(tmp_path):
    store = _store(tmp_path)
    claim = ClaimService(store).add_claim(
        "Habitus shapes patients' engagement with screening.", "background")
    ClaimService(store).mark_untestable(claim.claim_id, "1992 sociology monograph, not indexed")
    rep, row = _report_row(store, claim.claim_id)
    assert row.state == "untestable" and row.code == "u "
    assert row.untestable_reason == "1992 sociology monograph, not indexed"
    assert rep.counts["untestable"] == 1 and rep.counts["needs_support"] == 0


def test_clearing_the_marker_restores_needs_support(tmp_path):
    store = _store(tmp_path)
    claim = ClaimService(store).add_claim("A grey-literature assertion.", "other")
    ClaimService(store).mark_untestable(claim.claim_id, "policy report")
    ClaimService(store).mark_untestable(claim.claim_id, None)
    _rep, row = _report_row(store, claim.claim_id)
    assert row.state == "needs_support" and row.untestable_reason is None


def test_accepted_evidence_beats_the_untestable_marker(tmp_path):
    store = _store(tmp_path)
    claim = ClaimService(store).add_claim("LDCT reduces mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider([ProviderHit(pmid="1", doi="10.1/a", title="P")]),
                          library_index=StaticLibraryIndex()).literature_search("q", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    ClaimService(store).mark_untestable(claim.claim_id, "mis-marked")
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim.claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)
    DecisionService(store).decide(claim.claim_id, cand_id, "accept", "ok", rating_id=rec.rating_id)
    _rep, row = _report_row(store, claim.claim_id)
    assert row.state == "accepted"            # real accepted evidence always wins


def test_untestable_is_not_counted_as_needing_attention(tmp_path):
    store = _store(tmp_path)
    claim = ClaimService(store).add_claim("Theory-citing claim.", "other")
    ClaimService(store).mark_untestable(claim.claim_id, "book chapter")
    rep = ClaimReportService(store).report()
    out = render_markdown(rep)
    assert "need attention" not in out         # no false alarm for a correct citation
    assert "Untestable (out of indexed scope)" in out
    assert "book chapter" in out
    test_out = render_test_report(rep)
    assert "`[u]` untestable: 1" in test_out
    assert "missing_support" not in test_out   # the failure finding must not appear


def test_marker_requires_existing_claim_and_is_audited(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(Exception):
        ClaimService(store).mark_untestable("claim-nope", "x")
    claim = ClaimService(store).add_claim("Real claim.", "other")
    ClaimService(store).mark_untestable(claim.claim_id, "report, no DOI")
    events = [e.event for e in store.audit.entries()]
    assert "claim.untestable_set" in events
    assert store.audit.verify()
