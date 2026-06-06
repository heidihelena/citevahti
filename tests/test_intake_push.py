"""intake_push: preview item creation, DOI/PMID dedupe, no decision/map mutation."""

from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore
from citevahti.writeback import FakeWriteBackend, WritebackService


class FakeProvider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


def _setup(tmp_path, library_index=None):
    store = CiteVahtiStore(tmp_path)
    store.init()
    hits = [ProviderHit(pmid="111", doi="10.1/a", title="A"),
            ProviderHit(pmid="222", doi="10.1/b", title="B")]
    intake = IntakeService(store, provider=FakeProvider(hits), library_index=library_index)
    batch = intake.literature_search("q", question_id="q1")
    return store, batch.batch_id


def wb(store, backend=None, dedupe_index=None):
    return WritebackService(store, backend or FakeWriteBackend(), dedupe_index=dedupe_index)


def test_previews_item_creation(tmp_path):
    store, batch_id = _setup(tmp_path)
    diff = wb(store).intake_push(batch_id)
    assert len(diff.structured["create"]) == 2 and "create 2" in diff.proposed_changes[0]


def test_skips_already_in_library(tmp_path):
    store, batch_id = _setup(tmp_path)
    diff = wb(store, dedupe_index=StaticLibraryIndex(pmids=["111"])).intake_push(batch_id)
    created = {c["pmid"] for c in diff.structured["create"]}
    skipped = {sk["record_id"] for sk in diff.structured["skipped"]}
    assert "222" in created and "111" not in created and skipped


def test_confirmed_push_writes_via_fake(tmp_path):
    store, batch_id = _setup(tmp_path)
    s = wb(store)
    diff = s.intake_push(batch_id)
    res = s.intake_push(batch_id, dry_run=False, confirm_token=diff.confirm_token)
    assert res.applied and res.backend_kind == "local_addon"
    assert "zotero.write.applied" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


def test_no_inclusion_decision_or_map_mutation(tmp_path):
    store, batch_id = _setup(tmp_path)
    emap_before = store.load_evidence_map().model_dump()
    s = wb(store)
    diff = s.intake_push(batch_id)
    s.intake_push(batch_id, dry_run=False, confirm_token=diff.confirm_token)
    intake = store.load_intake(batch_id)
    assert all(h.decision is None for h in intake.hits)          # decisions untouched
    assert store.load_evidence_map().model_dump() == emap_before  # evidence map untouched
