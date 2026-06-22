"""P1 UX fixes from external QA: a human-only decision needs no `compare` step, and
the AI-off path raises a typed error (clean CLI message) rather than a traceback.
"""

import pytest

from citevahti import tools
from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore
from citevahti.validators.errors import AIUnavailableError


class _Provider:
    name = "pubmed"

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", count=1, email_present=True, rate_tier="3rps",
                                    hits=[ProviderHit(pmid="1", doi="10.1/a", title="T",
                                                      abstract="An abstract.")])


def _rated(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    cfg = store.load_config()
    cfg.ai_provenance.model_id = "m"
    cfg.ai_provenance.model_snapshot = "s"
    store.save_config(cfg)
    claim = ClaimService(store).add_claim("A claim.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(),
                          library_index=StaticLibraryIndex()).literature_search("q", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cid = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    rec = ClaimSupportEngine(store).support_start(claim.claim_id, cid)
    ClaimSupportEngine(store).support_commit_human(rec.rating_id, "directly_supports")
    return store, claim.claim_id, cid, rec.rating_id


def test_human_only_decision_needs_no_compare_step(tmp_path):
    # No AI rating, no support_compare() — deciding must still resolve (P1-2).
    store, claim_id, cand_id, rating_id = _rated(tmp_path)
    dec = DecisionService(store).decide(claim_id, cand_id, "accept", "supports",
                                        rating_id=rating_id)
    assert dec.final_decision == "accept"
    assert dec.final_support_status == "directly_supports"
    assert dec.agreement_status == "human_only"


def test_support_run_ai_off_raises_typed_error_not_traceback(tmp_path):
    # AI off + no rater injected → a typed AIUnavailableError the CLI catches cleanly (P1-1).
    store, claim_id, cand_id, rating_id = _rated(tmp_path)
    with pytest.raises(AIUnavailableError) as exc:
        tools.support_run_ai(rating_id, root=str(tmp_path))
    assert exc.value.code == "ai_unavailable"
    assert "human-only" in str(exc.value)
