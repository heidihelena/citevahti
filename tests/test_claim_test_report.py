"""The claim-test report formatter (the "manuscript as code" output).

Same blinding as everywhere else: the AI rating is shown only once the human has
rated; the per-claim finding is derived from the human value, never the AI value.
"""

import json

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.report import ClaimReportService, render_test_report
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
        [ProviderHit(pmid="21714641", title="NLST")]),
        library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return store, claim.claim_id, cand_id


def test_report_has_summary_and_per_claim_sections(tmp_path):
    store, claim_id, _ = _setup(tmp_path)
    rep = ClaimReportService(store).report()
    out = render_test_report(rep)
    assert "# Claim Test Report" in out
    assert "## Summary" in out and "## Per claim" in out
    assert "`[o]` needs support: 1" in out          # one unrated claim → needs support
    assert claim_id in out


def test_report_blinds_ai_until_human_rates(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.submit_ai_rating(rec.rating_id, "directly_supports")    # AI only, no human
    eng.support_compare(rec.rating_id)

    out = render_test_report(ClaimReportService(store).report())
    assert "hidden (blinded until human rates)" in out
    assert "directly_supports" not in out                       # AI value never leaks pre-human


def test_report_shows_finding_and_ai_after_human_rates(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.submit_ai_rating(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)

    out = render_test_report(ClaimReportService(store).report())
    assert "Finding: `support_direct`" in out                   # human-sourced finding label
    assert "AI rating: directly_supports" in out                # unblinded after human rated
