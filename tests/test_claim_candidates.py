"""Claim ↔ candidate linkage (ADR-0001 step 2): provenance kept, deduped, audited.

Linking connects a claim to the papers that entered consideration for it and
records why each was found. It asserts no support, decides nothing, and writes
nothing to Zotero. Dedupe is by normalized PMID/DOI (never title-only).
"""

import pytest

from citevahti.claims import CandidateService, ClaimService
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore
from citevahti.state.store import StateError


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    total_count=len(self.hits), email_present=True,
                                    rate_tier="3rps")


def _setup(tmp_path, hits=None):
    store = CiteVahtiStore(tmp_path)
    store.init()
    hits = hits or [
        ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873",
                    title="Reduced lung-cancer mortality with low-dose CT screening"),
        ProviderHit(pmid="222", doi="10.1/b", title="Another screening trial"),
    ]
    batch = IntakeService(store, provider=_Provider(hits),
                          library_index=StaticLibraryIndex()).literature_search(
        "low-dose CT lung cancer mortality", question_id="q1")
    claim = ClaimService(store).add_claim(
        "Low-dose CT screening reduces lung-cancer mortality.", "effectiveness")
    return store, claim.claim_id, batch.batch_id


def test_links_intake_hits_and_preserves_retrieval_provenance(tmp_path):
    store, claim_id, batch_id = _setup(tmp_path)
    rep = CandidateService(store).link_from_intake(claim_id, batch_id)
    assert rep.linked == 2 and rep.skipped_duplicates == 0 and rep.total_candidates == 2
    cc = store.load_candidates(claim_id)
    first = cc.candidates[0]
    assert first.claim_id == claim_id
    assert first.retrieval_query == "low-dose CT lung cancer mortality"
    assert first.retrieval_source == "pubmed"
    assert first.retrieval_rank == 0
    assert first.pmid == "21714641" and first.doi == "10.1056/NEJMoa1102873"


def test_linking_is_idempotent_by_pmid_doi(tmp_path):
    store, claim_id, batch_id = _setup(tmp_path)
    svc = CandidateService(store)
    svc.link_from_intake(claim_id, batch_id)
    rep2 = svc.link_from_intake(claim_id, batch_id)            # re-link same batch
    assert rep2.linked == 0 and rep2.skipped_duplicates == 2
    assert rep2.total_candidates == 2                          # no duplicates created


def test_record_id_filter_limits_linking(tmp_path):
    store, claim_id, batch_id = _setup(tmp_path)
    rep = CandidateService(store).link_from_intake(claim_id, batch_id, record_ids=["pmid:222"])
    assert rep.linked == 1
    cc = store.load_candidates(claim_id)
    assert {c.pmid for c in cc.candidates} == {"222"}


def test_linking_to_missing_claim_raises(tmp_path):
    store, _claim_id, batch_id = _setup(tmp_path)
    with pytest.raises(StateError):
        CandidateService(store).link_from_intake("claim-does-not-exist", batch_id)


def test_linking_from_missing_batch_raises(tmp_path):
    store, claim_id, _batch_id = _setup(tmp_path)
    with pytest.raises(StateError):
        CandidateService(store).link_from_intake(claim_id, "batch-nope")


def test_link_is_audited_and_chain_verifies(tmp_path):
    store, claim_id, batch_id = _setup(tmp_path)
    CandidateService(store).link_from_intake(claim_id, batch_id)
    assert "candidate.link" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


def test_linking_does_not_mutate_evidence_map(tmp_path):
    store, claim_id, batch_id = _setup(tmp_path)
    before = store.load_evidence_map().model_dump()
    CandidateService(store).link_from_intake(claim_id, batch_id)
    assert store.load_evidence_map().model_dump() == before    # no support asserted, nothing decided


def test_list_for_claim_with_no_candidates_is_empty(tmp_path):
    store, claim_id, _batch_id = _setup(tmp_path)
    cc = CandidateService(store).list_for_claim(claim_id)
    assert cc.claim_id == claim_id and cc.candidates == []


def test_already_in_zotero_flag_carried(tmp_path):
    hits = [ProviderHit(pmid="999", doi="10.1/z", title="Known paper")]
    store = CiteVahtiStore(tmp_path)
    store.init()
    # library index that reports the paper already present -> dedupe_status already_in_library
    idx = StaticLibraryIndex(pmids=["999"], dois=["10.1/z"])
    batch = IntakeService(store, provider=_Provider(hits), library_index=idx).literature_search(
        "q", question_id="q1")
    claim = ClaimService(store).add_claim("claim", "other")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cc = store.load_candidates(claim.claim_id)
    assert cc.candidates[0].already_in_zotero is True
