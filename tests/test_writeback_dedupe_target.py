"""Cross-boundary duplicate protection + intake_push hardening (Sev-4 fixes).

The library dedupe checks the LOCAL Zotero API; an item created via the Web API
may not be synced locally yet, so a paper can look "new" locally while already
existing on the write target. These tests pin that the validated write re-checks
the write target and refuses, and that generic intake_push enforces the same
rules (no duplicate_in_run, no identifier-less records, no write-target dups).
"""

import pytest

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
    FakeClaimSupportRater,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.schemas.common import Provenance
from citevahti.schemas.intake import IntakeHit, IntakeRecord
from citevahti.state import CiteVahtiStore
from citevahti.writeback import FakeWriteBackend, TransactionService, WritebackService
from citevahti.writeback.webapi import WebApiWriteBackend


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


def _accepted(tmp_path, pmid="21714641", doi="10.1056/NEJMoa1102873"):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider([ProviderHit(pmid=pmid, doi=doi, title="NLST")]),
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


def _commit(svc, decision_id, **kw):
    """Preview to get an approval token, then commit with it (the required flow)."""
    diff = svc.commit_for_decision(decision_id, dry_run=True, **kw)
    return svc.commit_for_decision(decision_id, dry_run=False, confirm_token=diff.confirm_token, **kw)


# ---- Sev-4a: write-target dedupe on the validated path ---------------------
def test_validated_write_refuses_duplicate_on_write_target(tmp_path):
    store, decision_id = _accepted(tmp_path)
    # the write target already has this DOI (created earlier via Web API, not synced locally)
    be = FakeWriteBackend(existing=[{"doi": "10.1056/NEJMoa1102873", "key": "OLD123"}])
    txn = _commit(TransactionService(store, be), decision_id)
    assert txn.status == "failed" and txn.error_code == "duplicate_on_write_target"
    assert txn.result["duplicate_keys"] == ["OLD123"]
    assert be.applied == []                       # nothing written


def test_validated_write_proceeds_when_target_is_clean(tmp_path):
    store, decision_id = _accepted(tmp_path)
    be = FakeWriteBackend()                        # empty target
    txn = _commit(TransactionService(store, be), decision_id)
    assert txn.status == "committed" and txn.result["created_keys"]


def test_dry_run_warns_about_write_target_duplicate(tmp_path):
    store, decision_id = _accepted(tmp_path)
    be = FakeWriteBackend(existing=[{"pmid": "21714641", "key": "OLD9"}])
    diff = TransactionService(store, be).commit_for_decision(decision_id, dry_run=True)
    assert any("already in the Zotero library" in w for w in diff.warnings)


class _NoCheck(FakeWriteBackend):
    def find_existing(self, pmid, doi):
        return None                                # available, but cannot verify


def test_uncheckable_target_is_refused_unless_overridden(tmp_path):
    # Sev-4b: a dedupe-unverified state must NOT proceed silently.
    store, decision_id = _accepted(tmp_path)
    txn = _commit(TransactionService(store, _NoCheck()), decision_id)
    assert txn.status == "failed" and txn.error_code == "dedupe_unverified"


def test_uncheckable_target_proceeds_with_explicit_override(tmp_path):
    store, decision_id = _accepted(tmp_path)
    txn = _commit(TransactionService(store, _NoCheck()), decision_id, allow_unverified_dedupe=True)
    assert txn.status == "committed"


def test_dry_run_warns_when_dedupe_unverified(tmp_path):
    store, decision_id = _accepted(tmp_path)
    diff = TransactionService(store, _NoCheck()).commit_for_decision(decision_id, dry_run=True)
    assert any("dedupe_unverified" in w for w in diff.warnings)


# ---- Sev-4b: intake_push hardening -----------------------------------------
def _intake_with(tmp_path, hits):
    store = CiteVahtiStore(tmp_path)
    store.init()
    rec = IntakeRecord(
        batch_id="b1", provider="pubmed", exact_query="q", run_at="2026-06-03T00:00:00+00:00",
        provenance=Provenance(tool="literature_search", tool_version="0.3.0",
                              ran_at="2026-06-03T00:00:00+00:00", config_hash="h"),
        hits=hits)
    store.save_intake(rec)
    return store


def test_intake_push_skips_duplicate_in_run_and_no_identifier(tmp_path):
    store = _intake_with(tmp_path, [
        IntakeHit(record_id="pmid:1", pmid="1", doi="10.1/a", title="Real", dedupe_status="new"),
        IntakeHit(record_id="pmid:1b", pmid="1", doi="10.1/a", title="Dup in run", dedupe_status="duplicate_in_run"),
        IntakeHit(record_id="title:x", pmid=None, doi=None, title="No identifiers", dedupe_status="new"),
    ])
    svc = WritebackService(store, FakeWriteBackend())
    diff = svc.intake_push("b1", dry_run=True)
    created_ids = [c["record_id"] for c in diff.structured["create"]]
    reasons = {s["record_id"]: s["reason"] for s in diff.structured["skipped"]}
    assert created_ids == ["pmid:1"]                        # only the clean record
    assert reasons["pmid:1b"] == "duplicate_in_run"
    assert reasons["title:x"] == "no_identifier"


def test_intake_push_skips_write_target_duplicate(tmp_path):
    store = _intake_with(tmp_path, [
        IntakeHit(record_id="pmid:1", pmid="1", doi="10.1/a", title="Already on target", dedupe_status="new"),
    ])
    be = FakeWriteBackend(existing=[{"pmid": "1", "key": "OLD"}])
    diff = WritebackService(store, be).intake_push("b1", dry_run=True)
    assert diff.structured["create"] == []
    assert diff.structured["skipped"][0]["reason"] == "already_on_write_target"


# ---- WebApi find_existing search (offline) ---------------------------------
class _SearchHttp:
    def __init__(self, items):
        self.items = items
        self.gets = []

    def get(self, url, headers=None, params=None):
        self.gets.append(params)
        return HttpResponse(200, _json=self.items)

    def post(self, *a, **k):
        raise AssertionError("find_existing must not POST")


def test_webapi_find_existing_matches_doi_and_pmid():
    http = _SearchHttp([{"key": "ZKEY1", "data": {"DOI": "10.1056/NEJMoa1102873",
                                                  "extra": "PMID: 21714641"}}])
    be = WebApiWriteBackend(http, api_key="k", user_id="123")
    assert be.find_existing(None, "10.1056/NEJMoa1102873") == ["ZKEY1"]
    assert be.find_existing("21714641", None) == ["ZKEY1"]
    assert be.find_existing("999", "10.9/nope") == []        # no match -> verified absent


def test_webapi_find_existing_unreachable_returns_none():
    class _Boom:
        def get(self, *a, **k):
            raise ProbeTransportError("offline")

        def post(self, *a, **k):
            raise AssertionError
    assert WebApiWriteBackend(_Boom(), "k", "1").find_existing("1", "10.1/a") is None
