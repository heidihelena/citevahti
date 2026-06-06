"""Agent-write boundary + review-required block (beta-hardening stress test).

A validated write must require a prior preview's approval token (no one-call API
write), and a write from a review_required intake batch must be blocked unless
explicitly overridden.
"""

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
    FakeClaimSupportRater,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.schemas.common import Provenance
from citevahti.schemas.intake import IntakeHit, IntakeRecord
from citevahti.state import CiteVahtiStore
from citevahti.writeback import FakeWriteBackend, TransactionService, WritebackService


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


def _accepted(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(
        [ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873", title="NLST")]),
        library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="directly_supports"))
    rec = eng.support_start(claim.claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)
    dec = DecisionService(store).decide(claim.claim_id, cand_id, "accept", "supports",
                                        rating_id=rec.rating_id)
    return store, dec.decision_id


# ---- Sev-4: agent-write boundary -------------------------------------------
def test_commit_without_token_is_refused(tmp_path):
    store, decision_id = _accepted(tmp_path)
    # a one-call API write (no prior preview token) must NOT reach the backend
    be = FakeWriteBackend()
    txn = TransactionService(store, be).commit_for_decision(decision_id, dry_run=False)
    assert txn.status == "failed" and txn.error_code == "missing_confirm_token"
    assert be.applied == []                          # nothing written


def test_commit_with_preview_token_writes(tmp_path):
    store, decision_id = _accepted(tmp_path)
    be = FakeWriteBackend()
    svc = TransactionService(store, be)
    diff = svc.commit_for_decision(decision_id, dry_run=True)      # user-visible preview
    txn = svc.commit_for_decision(decision_id, dry_run=False, confirm_token=diff.confirm_token)
    assert txn.status == "committed" and len(be.applied) == 1


def test_stale_or_wrong_token_is_refused(tmp_path):
    store, decision_id = _accepted(tmp_path)
    be = FakeWriteBackend()
    txn = TransactionService(store, be).commit_for_decision(
        decision_id, dry_run=False, confirm_token="not-a-real-token")
    assert txn.status == "failed" and be.applied == []   # token didn't match a pending preview


# ---- Sev-2/3: review-required batches are blocked from writing --------------
def _review_batch(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    rec = IntakeRecord(
        batch_id="b1", provider="pubmed", exact_query="x AND (", run_at="2026-06-03T00:00:00+00:00",
        provenance=Provenance(tool="literature_search", tool_version="0.4.0",
                              ran_at="2026-06-03T00:00:00+00:00", config_hash="h"),
        review_required=True, warnings=["outputmessages: Unbalanced parentheses."],
        hits=[IntakeHit(record_id="pmid:1", pmid="1", doi="10.1/a", title="A", dedupe_status="new")])
    store.save_intake(rec)
    return store


def test_review_required_batch_blocks_commit(tmp_path):
    store = _review_batch(tmp_path)
    svc = WritebackService(store, FakeWriteBackend())
    diff = svc.intake_push("b1", dry_run=True)            # preview is fine
    res = svc.intake_push("b1", dry_run=False, confirm_token=diff.confirm_token)
    assert res.applied is False and res.error_code == "batch_review_required"


def test_review_required_can_be_overridden(tmp_path):
    store = _review_batch(tmp_path)
    svc = WritebackService(store, FakeWriteBackend())
    diff = svc.intake_push("b1", dry_run=True)
    res = svc.intake_push("b1", dry_run=False, confirm_token=diff.confirm_token,
                          allow_review_required=True)
    assert res.applied is True
