"""retraction_scan: DOI/PMID detection, no title-only, honest degradation, flags."""

from citevahti.corpus import CorpusItem, SnapshotService, StaticCorpusSource
from citevahti.evidence import EvidenceMapService
from citevahti.retraction import FakeRetractionProvider, RetractionScanService
from citevahti.schemas.common import ItemRef
from citevahti.schemas.evidence_map import Attachment, EvidenceMap, Node
from citevahti.state import CiteVahtiStore


def store_init(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    return store


def emap_with_study(store, citekey="smith2020"):
    svc = EvidenceMapService(store)
    emap = EvidenceMap()
    svc.add_node(emap, Node(node_id="s1", type="study",
                            item=ItemRef(zotero_key="K1", citekey=citekey)))
    svc.add_attachment(emap, Attachment(attachment_id="a1", kind="assessment",
                                        scheme_kind="RoB2", study_node_id="s1"))
    svc.rebuild_reverse_index(emap)
    svc.save(emap)


def make_snapshot(store, items):
    SnapshotService(store, StaticCorpusSource(items)).snapshot(label="s")


def test_detects_doi_retraction(tmp_path):
    store = store_init(tmp_path)
    svc = RetractionScanService(store, FakeRetractionProvider(retracted_dois=["10.1/x"]))
    rep = svc.scan({"dois": ["10.1/X"]})           # case-insensitive
    assert len(rep.retracted) == 1 and rep.retracted[0].doi == "10.1/X"


def test_detects_pmid_retraction(tmp_path):
    store = store_init(tmp_path)
    svc = RetractionScanService(store, FakeRetractionProvider(retracted_pmids=["111"]))
    rep = svc.scan({"pmids": ["111"]})
    assert len(rep.retracted) == 1 and rep.retracted[0].pmid == "111"


def test_does_not_detect_by_title_alone(tmp_path):
    store = store_init(tmp_path)
    make_snapshot(store, [CorpusItem(zotero_key="K9", citekey="nodoi", title="Retracted paper")])
    svc = RetractionScanService(store, FakeRetractionProvider(retracted_dois=["10.1/x"]))
    rep = svc.scan({"citekeys": ["nodoi"]})        # no DOI/PMID -> not scanned
    assert rep.retracted == []
    assert any("no DOI/PMID" in w for w in rep.warnings)


def test_provider_unavailable_degrades(tmp_path):
    store = store_init(tmp_path)
    svc = RetractionScanService(store, FakeRetractionProvider(available=False))
    rep = svc.scan({"dois": ["10.1/x"]})
    assert rep.status == "degraded" and rep.error_code == "provider_unavailable"
    assert rep.retracted == []


def _setup_citekey_retraction(tmp_path):
    store = store_init(tmp_path)
    emap_with_study(store, "smith2020")
    make_snapshot(store, [CorpusItem(zotero_key="K1", citekey="smith2020", doi="10.1/x", pmid="111")])
    svc = RetractionScanService(store, FakeRetractionProvider(retracted_dois=["10.1/x"]))
    return store, svc


def test_mark_stale_false_does_not_mutate(tmp_path):
    store, svc = _setup_citekey_retraction(tmp_path)
    before = len(store.load_evidence_map().attachments)
    rep = svc.scan({"citekeys": ["smith2020"]}, mark_stale=False)
    assert len(rep.retracted) == 1
    assert len(store.load_evidence_map().attachments) == before


def test_mark_stale_true_adds_retraction_and_stale_flags(tmp_path):
    store, svc = _setup_citekey_retraction(tmp_path)
    rep = svc.scan({"citekeys": ["smith2020"]}, mark_stale=True)
    assert rep.retraction_flags_added and rep.staleness_flags_added
    kinds = [a.kind for a in store.load_evidence_map().attachments]
    assert "retraction_flag" in kinds and "staleness_flag" in kinds
    assert rep.affected.attachments == ["a1"]      # affected assessment via reverse index


def test_audit_event_and_verify(tmp_path):
    store, svc = _setup_citekey_retraction(tmp_path)
    rep = svc.scan({"citekeys": ["smith2020"]}, mark_stale=True)
    assert rep.audit_event_id is not None
    assert store.audit.verify() is True
