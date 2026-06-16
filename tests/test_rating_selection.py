"""Regression: with more than one support rating per (claim, candidate), the report and
the panel must select the *most advanced/recent* one — not an arbitrary uuid-sorted match.

`support_start` mints a fresh rating id each call, so a pair can accumulate several
ratings on disk. The old `setdefault(...)  # last wins` actually kept the first in uuid
order, which could surface a stale or blank rating in the report/panel.
"""

from citevahti.claims import CandidateService, ClaimService, ClaimSupportEngine
from citevahti.claims.support import rating_preference_key
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.panel.server import _find_rating_for
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.report import ClaimReportService
from citevahti.state import CiteVahtiStore


class _Provider:
    name = "pubmed"

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(
            status="ok", count=1, email_present=True, rate_tier="3rps",
            hits=[ProviderHit(pmid="21714641", doi="10.1/x", title="NLST")])


def _seed(tmp_path):
    store = CiteVahtiStore(str(tmp_path))
    store.init()
    claim = ClaimService(store).add_claim("LDCT reduces mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(),
                          library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return store, claim.claim_id, cand_id


def test_committed_rating_wins_over_a_later_blank_one(tmp_path):
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store)
    committed = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(committed.rating_id, value="directly_supports")
    # a second support_start for the same pair leaves a fresh, unrated rating on disk
    blank = eng.support_start(claim_id, cand_id)
    assert blank.rating_id != committed.rating_id

    picked = _find_rating_for(store, claim_id, cand_id)
    assert picked.rating_id == committed.rating_id          # the committed one, not the blank
    assert picked.human_rating and picked.human_rating.value == "directly_supports"

    # and the report agrees (no longer an arbitrary uuid-sorted pick)
    row = next(r for r in ClaimReportService(store).report().rows if r.claim_id == claim_id)
    ev = next(e for e in row.evidence if e.candidate_id == cand_id)
    assert ev.human_support == "directly_supports"


def test_preference_key_orders_advanced_over_blank(tmp_path):
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store)
    blank = eng.support_start(claim_id, cand_id)
    committed = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(committed.rating_id, value="partially_supports")
    committed = store.load_support_rating(committed.rating_id)
    assert rating_preference_key(committed) > rating_preference_key(blank)
