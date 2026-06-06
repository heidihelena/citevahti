"""Follow-ups: intake_push commits record a transaction + undo; review_required flag."""

from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.schemas.common import Provenance
from citevahti.schemas.intake import IntakeHit, IntakeRecord
from citevahti.state import CiteVahtiStore
from citevahti.writeback import FakeWriteBackend, WritebackService


def _intake(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    rec = IntakeRecord(
        batch_id="b1", provider="pubmed", exact_query="q", run_at="2026-06-03T00:00:00+00:00",
        provenance=Provenance(tool="literature_search", tool_version="0.4.0",
                              ran_at="2026-06-03T00:00:00+00:00", config_hash="h"),
        hits=[IntakeHit(record_id="pmid:1", pmid="1", doi="10.1/a", title="A", dedupe_status="new"),
              IntakeHit(record_id="pmid:2", pmid="2", doi="10.1/b", title="B", dedupe_status="new")])
    store.save_intake(rec)
    return store


def test_committed_intake_push_records_transaction_with_undo(tmp_path):
    store = _intake(tmp_path)
    svc = WritebackService(store, FakeWriteBackend())
    diff = svc.intake_push("b1", dry_run=True)                     # mints a token
    res = svc.intake_push("b1", dry_run=False, confirm_token=diff.confirm_token)
    assert res.applied and res.result["created_keys"]
    txn_id = res.result["transaction_id"]
    txn = store.load_transaction(txn_id)
    assert txn.kind == "intake_push" and txn.validated is False and txn.status == "committed"
    assert txn.undo_snapshot["delete_keys"] == res.result["created_keys"]
    assert "zotero.transaction.committed" in [e.event for e in store.audit.entries()]


def test_dry_run_intake_push_records_no_transaction(tmp_path):
    store = _intake(tmp_path)
    svc = WritebackService(store, FakeWriteBackend())
    svc.intake_push("b1", dry_run=True)
    assert store.list_transactions() == []


# ---- review_required (Sev-3) ------------------------------------------------
class _WarnProvider:
    name = "pubmed"

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(
            status="warnings", hits=[ProviderHit(pmid="1", doi="10.1/a", title="A")],
            count=1, total_count=1, query_translation='"lung neoplasms"[MeSH]',
            email_present=True, rate_tier="3rps",
            warnings=["outputmessages: Unbalanced quotes or parentheses."])


class _CleanProvider:
    name = "pubmed"

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=[ProviderHit(pmid="1", doi="10.1/a", title="A")],
                                    count=1, total_count=1, email_present=True, rate_tier="3rps")


def test_warnings_set_review_required(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    rec = IntakeService(store, provider=_WarnProvider(),
                        library_index=StaticLibraryIndex()).literature_search("x AND (", question_id="q1")
    assert rec.review_required is True and rec.status == "ok"


def test_clean_query_is_not_review_required(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    rec = IntakeService(store, provider=_CleanProvider(),
                        library_index=StaticLibraryIndex()).literature_search("lung cancer", question_id="q1")
    assert rec.review_required is False
