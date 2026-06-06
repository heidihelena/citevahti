"""literature_search: staging, exact query, dedupe, degradation, audit."""

from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore


class FakeProvider:
    name = "pubmed"

    def __init__(self, result):
        self._result = result

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return self._result


def ok(hits, **kw):
    return ProviderSearchResult(status="ok", hits=hits, count=len(hits),
                                email_present=True, rate_tier="3rps", **kw)


def hit(pmid=None, doi=None, title="A study"):
    return ProviderHit(pmid=pmid, doi=doi, title=title, authors=["A B"],
                       journal="J", year=2020, abstract="abs")


def service(tmp_path, result, library_index=None):
    store = CiteVahtiStore(tmp_path)
    store.init()
    return IntakeService(store, provider=FakeProvider(result), library_index=library_index), store


def test_stages_pubmed_results_to_intake_file(tmp_path):
    svc, store = service(tmp_path, ok([hit("111"), hit("222")]))
    rec = svc.literature_search("cancer")
    assert rec.status == "ok" and len(rec.hits) == 2
    assert store.list_intake() == [rec.batch_id]
    assert store.load_intake(rec.batch_id).result_count == 2


def test_stores_exact_query_unchanged(tmp_path):
    svc, _ = service(tmp_path, ok([hit("111")]))
    q = '("heart failure"[MeSH]) AND 2020:2023[dp]'
    rec = svc.literature_search(q)
    assert rec.exact_query == q and rec.query == q


def test_stores_provider_env_and_provenance(tmp_path):
    svc, _ = service(tmp_path, ok([hit("111")], api_key_present=False))
    rec = svc.literature_search("cancer")
    assert rec.provider == "pubmed" and rec.run_at and rec.last_run_at is None
    assert rec.ncbi_email_present is True and rec.rate_tier == "3rps"
    assert rec.provenance is not None and rec.provenance.tool == "literature_search"


def test_hits_decision_is_null(tmp_path):
    svc, _ = service(tmp_path, ok([hit("111")]))
    rec = svc.literature_search("cancer")
    assert all(h.decision is None for h in rec.hits)


def test_dedupes_duplicate_pmid_within_run(tmp_path):
    svc, _ = service(tmp_path, ok([hit("111"), hit("111")]))
    rec = svc.literature_search("cancer")
    assert rec.hits[0].dedupe_status == "new"
    assert rec.hits[1].dedupe_status == "duplicate_in_run"


def test_dedupes_duplicate_doi_within_run(tmp_path):
    svc, _ = service(tmp_path, ok([hit(doi="10.1/x"), hit(doi="10.1/X")]))  # case-insensitive
    rec = svc.literature_search("cancer")
    assert rec.hits[1].dedupe_status == "duplicate_in_run"


def test_dedupes_against_prior_intake(tmp_path):
    svc, _ = service(tmp_path, ok([hit("111")]))
    svc.literature_search("cancer", question_id="q1")
    rec2 = svc.literature_search("cancer", question_id="q2")
    assert rec2.hits[0].dedupe_status == "already_in_prior_intake"


def test_dedupes_against_library_by_pmid(tmp_path):
    svc, _ = service(tmp_path, ok([hit("999")]), library_index=StaticLibraryIndex(pmids=["999"]))
    rec = svc.literature_search("cancer")
    assert rec.hits[0].dedupe_status == "already_in_library"


def test_dedupes_against_library_by_doi(tmp_path):
    svc, _ = service(tmp_path, ok([hit(doi="10.1/X")]),
                     library_index=StaticLibraryIndex(dois=["10.1/x"]))
    rec = svc.literature_search("cancer")
    assert rec.hits[0].dedupe_status == "already_in_library"


def test_does_not_dedupe_by_title_alone(tmp_path):
    # no pmid/doi -> library cannot claim it's already present
    svc, _ = service(tmp_path, ok([hit(title="Some Title")]),
                     library_index=StaticLibraryIndex(pmids=["111"], dois=["10.1/x"]))
    rec = svc.literature_search("cancer")
    assert rec.hits[0].dedupe_status == "new"


def test_zotero_unavailable_degrades_library_dedupe_but_stages(tmp_path):
    svc, store = service(tmp_path, ok([hit("111")]),
                         library_index=StaticLibraryIndex(available=False))
    rec = svc.literature_search("cancer")
    assert rec.status == "ok"                      # still staged
    assert rec.library_dedupe_status == "degraded"
    assert rec.hits[0].dedupe_status == "new"
    assert store.list_intake() == [rec.batch_id]


def test_missing_env_degrades_with_no_fake_hits(tmp_path):
    svc, store = service(tmp_path, ProviderSearchResult(
        status="missing_ncbi_email", email_present=False,
        remediation="Set NCBI_EMAIL ..."))
    rec = svc.literature_search("cancer")
    assert rec.status == "degraded" and rec.error_code == "missing_ncbi_email"
    assert rec.hits == []
    assert store.list_intake() == []               # nothing staged


def test_audit_event_written_and_verifies(tmp_path):
    svc, store = service(tmp_path, ok([hit("111")]))
    rec = svc.literature_search("cancer")
    assert rec.audit_event_id is not None
    assert "intake.write" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


# ---- CLI --json output (consumed by the VS Code "Change reference" flow) -----
def test_cli_literature_search_json_emits_batch_and_hits(tmp_path, monkeypatch, capsys):
    import json
    from citevahti import tools as _tools
    from citevahti.cli import main

    svc, store = service(tmp_path, ok([hit("111", title="Alpha"), hit("222", title="Beta")]))
    rec = svc.literature_search("cancer")
    monkeypatch.setattr(_tools, "literature_search", lambda *a, **k: rec)

    rc = main(["--root", str(tmp_path), "literature-search", "--query", "cancer", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["status"] == "ok" and out["batch_id"] == rec.batch_id
    assert len(out["hits"]) == 2 and all(h["record_id"] for h in out["hits"])
    assert {h["title"] for h in out["hits"]} == {"Alpha", "Beta"}


def test_cli_link_candidates_json_links_staged_hits_to_a_claim(tmp_path, capsys):
    import json
    from citevahti.claims import ClaimService
    from citevahti.cli import main

    svc, store = service(tmp_path, ok([hit("111", title="Alpha")]))
    rec = svc.literature_search("cancer")
    claim = ClaimService(store).add_claim("a claim needing a better reference", "background")

    rc = main(["--root", str(tmp_path), "claim-link-candidates",
               "--claim-id", claim.claim_id, "--intake-batch-id", rec.batch_id, "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["claim_id"] == claim.claim_id
    assert out["linked"] == 1 and out["total_candidates"] == 1
