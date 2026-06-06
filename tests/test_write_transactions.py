"""Decision-gated write transactions + undo (ADR-0001 step 5).

A validated write exists only for an ACCEPT decision, always carries its §6 chain
(claim · candidate · decision · provenance · transaction · audit · undo), and can
be undone (deleting only the keys it created). Fully offline (fake backend).
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
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore
from citevahti.state.store import StateError
from citevahti.writeback import (
    FakeWriteBackend,
    TransactionError,
    TransactionService,
    UnavailableBackend,
)


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


def _setup(tmp_path, hit=None):
    store = CiteVahtiStore(tmp_path)
    store.init()
    hit = hit or ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873", title="NLST")
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider([hit]),
                          library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return store, claim.claim_id, cand_id


def _accept(store, claim_id, cand_id, support="directly_supports"):
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value=support))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, support)
    eng.support_compare(rec.rating_id)        # human_only -> resolved
    return DecisionService(store).decide(
        claim_id, cand_id, "accept", "supports the claim", rating_id=rec.rating_id)


def _commit(svc, decision_id, **kw):
    """Preview to get an approval token, then commit with it (the required flow)."""
    diff = svc.commit_for_decision(decision_id, dry_run=True, **kw)
    return svc.commit_for_decision(decision_id, dry_run=False, confirm_token=diff.confirm_token, **kw)


# ---- dry-run preview -------------------------------------------------------
def test_dry_run_previews_without_writing(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    be = FakeWriteBackend()
    diff = TransactionService(store, be).commit_for_decision(dec.decision_id, dry_run=True)
    assert diff.dry_run is True and diff.proposed_changes
    assert be.applied == []                         # nothing written
    assert store.list_transactions() == []          # no transaction persisted on a preview


# ---- validated commit ------------------------------------------------------
def test_commit_creates_transaction_with_full_chain(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    be = FakeWriteBackend()
    txn = _commit(TransactionService(store, be), dec.decision_id, collection_key="COLL1")
    assert txn.status == "committed" and txn.validated is True
    assert txn.claim_id == claim_id and txn.candidate_id == cand_id
    assert txn.decision_id == dec.decision_id        # §6 chain complete
    assert txn.result["created_keys"]                # something was created
    assert txn.undo_snapshot["delete_keys"] == txn.result["created_keys"]
    assert len(be.applied) == 1


def test_decision_write_token_is_bound_to_collection_key(tmp_path):
    store, _claim_id, _cand_id = _setup(tmp_path)
    dec = _accept(store, _claim_id, _cand_id)
    be = FakeWriteBackend()
    svc = TransactionService(store, be)
    diff = svc.commit_for_decision(dec.decision_id, dry_run=True)
    txn = svc.commit_for_decision(
        dec.decision_id, collection_key="COLL1", dry_run=False,
        confirm_token=diff.confirm_token)
    assert txn.status == "failed"
    assert txn.error_code == "payload_changed_token_invalid"
    assert be.applied == []


def test_commit_refused_unless_decision_is_accept(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    # a needs_second_review decision (discordant, unresolved) is not writable
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="does_not_support"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    # no AI run -> human_only is resolved; force a needs_second_review decision instead
    dec = DecisionService(store).decide(claim_id, cand_id, "needs_second_review",
                                        "hold", rating_id=rec.rating_id)
    with pytest.raises(TransactionError):
        TransactionService(store, FakeWriteBackend()).commit_for_decision(
            dec.decision_id, dry_run=False)


def test_commit_refuses_candidate_without_identifier(tmp_path):
    # a candidate with neither PMID nor DOI cannot be written (anti-fabrication)
    store, claim_id, cand_id = _setup(
        tmp_path, hit=ProviderHit(pmid=None, doi=None, title="No identifiers"))
    dec = _accept(store, claim_id, cand_id)
    with pytest.raises(TransactionError):
        TransactionService(store, FakeWriteBackend()).commit_for_decision(
            dec.decision_id, dry_run=False)


def test_unavailable_backend_records_failed_transaction(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    txn = _commit(TransactionService(store, UnavailableBackend()), dec.decision_id)
    assert txn.status == "failed" and txn.error_code == "write_layer_unavailable"
    assert txn.undo_snapshot == {}                   # nothing to undo


def test_cli_claim_commit_json_dry_run_emits_diff(tmp_path, capsys):
    import json as _json

    from citevahti.cli import main
    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    main(["--root", str(tmp_path), "claim-commit", "--decision-id", dec.decision_id, "--json"])
    diff = _json.loads(capsys.readouterr().out)        # the VS Code extension parses this
    assert "confirm_token" in diff and "warnings" in diff and "proposed_changes" in diff


def test_cli_commit_without_token_does_not_auto_write(tmp_path, capsys):
    """Sev-4 guard: --commit without --confirm-token must NOT one-call write.

    Programmatic (--json) callers get preview_required + must replay the token;
    nothing is committed."""
    import json as _json

    from citevahti.cli import main
    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    rc = main(["--root", str(tmp_path), "claim-commit", "--decision-id", dec.decision_id,
               "--commit", "--json"])
    out = _json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["error_code"] == "missing_confirm_token" and out["status"] == "preview_required"
    assert "confirm_token" in out
    # and no transaction was committed
    from citevahti import tools
    assert tools.list_transactions(root=str(tmp_path)) == []


def test_cli_commit_returns_nonzero_when_transaction_fails(tmp_path, capsys):
    from types import SimpleNamespace
    from citevahti import tools
    from citevahti.cli import _cmd_claim_commit

    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    # preview-first: get a real confirm token, then commit (no backend -> fails cleanly)
    preview = tools.commit_decision(dec.decision_id, collection_key="COLL1",
                                    dry_run=True, root=str(tmp_path))
    rc = _cmd_claim_commit(SimpleNamespace(
        decision_id=dec.decision_id, collection_key="COLL1", commit=True,
        confirm_token=preview.confirm_token, allow_unverified_dedupe=False,
        json=False, root=str(tmp_path)))
    out = capsys.readouterr().out
    assert rc == 1
    assert "write failed:" in out


# ---- undo ------------------------------------------------------------------
def test_undo_deletes_only_created_keys(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    be = FakeWriteBackend()
    svc = TransactionService(store, be)
    txn = _commit(svc, dec.decision_id)
    created = txn.result["created_keys"]
    undone = svc.undo(txn.transaction_id)
    assert undone.status == "undone" and undone.undone_at
    assert be.undone == [{"delete_keys": created, "library": "personal", "collection_key": None}]
    assert undone.result["undo"]["deleted_keys"] == created


def test_cannot_undo_a_non_committed_transaction(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    svc = TransactionService(store, FakeWriteBackend())
    txn = _commit(svc, dec.decision_id)
    svc.undo(txn.transaction_id)
    with pytest.raises(TransactionError):
        svc.undo(txn.transaction_id)                 # already undone


def test_undo_on_unavailable_backend_is_recorded_not_silent(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    # commit with a working backend, then try to undo through an unavailable one
    txn = _commit(TransactionService(store, FakeWriteBackend()), dec.decision_id)
    out = TransactionService(store, UnavailableBackend()).undo(txn.transaction_id)
    assert out.status == "committed"                 # not silently marked undone
    assert out.error_code == "undo_unavailable"
    assert "zotero.transaction.undo_failed" in [e.event for e in store.audit.entries()]


def test_successful_retry_clears_prior_undo_failure_fields(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    txn = _commit(TransactionService(store, FakeWriteBackend()), dec.decision_id)
    failed = TransactionService(store, UnavailableBackend()).undo(txn.transaction_id)
    assert failed.status == "committed" and failed.error_code == "undo_unavailable"
    undone = TransactionService(store, FakeWriteBackend()).undo(txn.transaction_id)
    assert undone.status == "undone"
    assert undone.error_code is None and undone.remediation is None


# ---- audit + isolation -----------------------------------------------------
def test_transaction_is_audited_and_chain_verifies(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    dec = _accept(store, claim_id, cand_id)
    svc = TransactionService(store, FakeWriteBackend())
    txn = _commit(svc, dec.decision_id)
    svc.undo(txn.transaction_id)
    events = [e.event for e in store.audit.entries()]
    assert "zotero.transaction.committed" in events and "zotero.transaction.undone" in events
    assert store.audit.verify() is True


def test_commit_for_missing_decision_raises(tmp_path):
    store, _claim_id, _cand_id = _setup(tmp_path)
    with pytest.raises(StateError):
        TransactionService(store, FakeWriteBackend()).commit_for_decision("dec-nope", dry_run=False)


# ---- WebApi undo deletes only recorded keys, version-checked ---------------
class _UndoHttp:
    """Fake Zotero Web API: GET returns a version; DELETE records the call."""

    def __init__(self, version=5, delete_status=204):
        self.version = version
        self.delete_status = delete_status
        self.deletes = []

    def get(self, url, headers=None, params=None):
        from citevahti.probe.client import HttpResponse
        return HttpResponse(200, _json={"key": url.rsplit("/", 1)[-1], "version": self.version})

    def post(self, url, json=None, headers=None):
        raise AssertionError("undo must not POST")

    def delete(self, url, headers=None):
        from citevahti.probe.client import HttpResponse
        self.deletes.append({"url": url, "ius": (headers or {}).get("If-Unmodified-Since-Version")})
        return HttpResponse(self.delete_status, text="")


def test_webapi_undo_deletes_recorded_keys_with_version_guard():
    from citevahti.writeback.webapi import WebApiWriteBackend
    http = _UndoHttp(version=7)
    be = WebApiWriteBackend(http, api_key="SECRET", user_id="123")
    out = be.undo({"delete_keys": ["AAAA1111", "BBBB2222"], "library": "personal"})
    assert out["deleted_keys"] == ["AAAA1111", "BBBB2222"] and out["deleted"] == 2
    # each DELETE carried the item's version so a concurrent edit would abort it
    assert all(d["ius"] == "7" for d in http.deletes)
    assert http.deletes[0]["url"].endswith("/users/123/items/AAAA1111")


def test_webapi_undo_skips_items_modified_since_create():
    from citevahti.writeback.webapi import WebApiWriteBackend
    http = _UndoHttp(version=7, delete_status=412)        # 412 = precondition failed
    be = WebApiWriteBackend(http, api_key="SECRET", user_id="123")
    out = be.undo({"delete_keys": ["AAAA1111"], "library": "personal"})
    assert out["deleted"] == 0
    assert out["skipped"][0]["reason"] == "modified_since_create"   # never clobber a user edit
