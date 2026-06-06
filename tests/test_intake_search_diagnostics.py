"""IntakeService surfaces PubMed diagnostics (total, query translation, warnings).

A 'warnings' search still stages hits (it succeeded with caveats); a hard query
error degrades and is NOT persisted with fabricated hits.
"""

from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore


class _Provider:
    name = "pubmed"

    def __init__(self, result):
        self._result = result

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return self._result


def _store(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    return s


def test_warnings_search_stages_and_carries_diagnostics(tmp_path):
    store = _store(tmp_path)
    res = ProviderSearchResult(
        status="warnings", hits=[ProviderHit(pmid="111", doi="10.1/a", title="A")],
        count=1, total_count=4137, query_translation='"lung neoplasms"[MeSH]',
        email_present=True, rate_tier="3rps",
        warnings=["outputmessages: Unbalanced quotes or parentheses."])
    svc = IntakeService(store, provider=_Provider(res), library_index=StaticLibraryIndex())
    rec = svc.literature_search("lung cancer AND (", question_id="q1")
    assert rec.status == "ok"                      # staged, with caveats
    assert rec.total_count == 4137 and rec.result_count == 1
    assert rec.query_translation == '"lung neoplasms"[MeSH]'
    assert any("Unbalanced" in w for w in rec.warnings)
    assert len(rec.hits) == 1


def test_query_error_degrades_and_is_not_persisted_with_hits(tmp_path):
    store = _store(tmp_path)
    res = ProviderSearchResult(status="pubmed_query_error", hits=[], count=0,
                               email_present=True, rate_tier="3rps",
                               errors=["bad query"], remediation="fix the parentheses")
    svc = IntakeService(store, provider=_Provider(res), library_index=StaticLibraryIndex())
    rec = svc.literature_search("AND (", question_id="q1")
    assert rec.status == "degraded" and rec.error_code == "pubmed_query_error"
    assert rec.hits == [] and rec.remediation
