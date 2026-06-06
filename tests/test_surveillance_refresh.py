"""surveillance_refresh: last-run baseline, query preservation, dedupe, degradation."""

from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore


class FakeProvider:
    name = "pubmed"

    def __init__(self, result):
        self.result = result

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return self.result


def ok(hits):
    return ProviderSearchResult(status="ok", hits=hits, count=len(hits),
                                email_present=True, rate_tier="3rps")


def hit(pmid=None, doi=None, title="A study"):
    return ProviderHit(pmid=pmid, doi=doi, title=title, year=2020)


def saved(tmp_path, baseline_hits, library_index=None):
    store = CiteVahtiStore(tmp_path)
    store.init()
    svc = IntakeService(store, provider=FakeProvider(ok(baseline_hits)), library_index=library_index)
    original = svc.literature_search("cancer[Title]", question_id="q1")
    return svc, store, original


def test_finds_saved_query_and_uses_run_at_baseline(tmp_path):
    svc, _, original = saved(tmp_path, [hit("111")])
    svc.provider = FakeProvider(ok([hit("222")]))
    rec = svc.surveillance_refresh("q1")
    assert rec.status == "ok"
    expected = original.run_at[:10].replace("-", "/")
    assert rec.baseline_date == expected               # baseline from saved run_at, not a snapshot


def test_preserves_original_and_stores_both_queries(tmp_path):
    svc, _, original = saved(tmp_path, [hit("111")])
    svc.provider = FakeProvider(ok([hit("222")]))
    rec = svc.surveillance_refresh("q1")
    assert rec.exact_query == original.exact_query == "cancer[Title]"
    assert rec.exact_query_sent != rec.exact_query
    assert "cancer[Title]" in rec.exact_query_sent and "Date - Publication" in rec.exact_query_sent


def test_stages_only_new_hits(tmp_path):
    svc, store, _ = saved(tmp_path, [hit("111")])
    svc.provider = FakeProvider(ok([hit("222")]))
    rec = svc.surveillance_refresh("q1")
    assert rec.hits[0].dedupe_status == "new"
    assert all(h.decision is None for h in rec.hits)
    assert rec.batch_id in store.list_intake()


def test_dedupes_against_prior_intake(tmp_path):
    svc, _, _ = saved(tmp_path, [hit("111")])
    svc.provider = FakeProvider(ok([hit("111")]))     # already in the saved batch
    rec = svc.surveillance_refresh("q1")
    assert rec.hits[0].dedupe_status == "already_in_prior_intake"


def test_dedupes_against_library(tmp_path):
    svc, _, _ = saved(tmp_path, [hit("111")], library_index=StaticLibraryIndex(pmids=["333"]))
    svc.provider = FakeProvider(ok([hit("333")]))
    rec = svc.surveillance_refresh("q1")
    assert rec.hits[0].dedupe_status == "already_in_library"


def test_duplicate_in_run_marked(tmp_path):
    svc, _, _ = saved(tmp_path, [hit("111")])
    svc.provider = FakeProvider(ok([hit("222"), hit("222")]))
    rec = svc.surveillance_refresh("q1")
    assert rec.hits[1].dedupe_status == "duplicate_in_run"


def test_missing_query_id_fails_cleanly(tmp_path):
    svc, store, _ = saved(tmp_path, [hit("111")])
    n_before = len(store.list_intake())
    rec = svc.surveillance_refresh("does_not_exist")
    assert rec.status == "degraded" and rec.error_code == "query_not_found"
    assert rec.remediation
    assert len(store.list_intake()) == n_before        # nothing staged


def test_missing_email_degrades_no_fake_hits(tmp_path):
    svc, store, _ = saved(tmp_path, [hit("111")])
    n_before = len(store.list_intake())
    svc.provider = FakeProvider(ProviderSearchResult(
        status="missing_ncbi_email", email_present=False, remediation="set NCBI_EMAIL"))
    rec = svc.surveillance_refresh("q1")
    assert rec.status == "degraded" and rec.error_code == "missing_ncbi_email"
    assert rec.hits == [] and len(store.list_intake()) == n_before


def test_audit_event_and_verify(tmp_path):
    svc, store, _ = saved(tmp_path, [hit("111")])
    svc.provider = FakeProvider(ok([hit("222")]))
    rec = svc.surveillance_refresh("q1")
    assert rec.audit_event_id is not None
    assert store.audit.verify() is True
