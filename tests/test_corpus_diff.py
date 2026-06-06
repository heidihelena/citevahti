"""corpus_diff: add/remove/change detection, continuity, reverse-index, staleness."""

from citevahti.corpus import CorpusDiffService, CorpusItem, SnapshotService, StaticCorpusSource
from citevahti.evidence import EvidenceMapService
from citevahti.schemas.common import ItemRef
from citevahti.schemas.evidence_map import Attachment, EvidenceMap, Link, Node
from citevahti.state import CiteVahtiStore

from conftest import make_grade_rating


def ci(zk, ck="smith2020", title="A study", doi="10.1/x", pmid="111", year=2020, ft=None):
    return CorpusItem(zotero_key=zk, citekey=ck, title=title, doi=doi, pmid=pmid, year=year,
                      fulltext_hash=ft)


def store_with(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    return store


def snap(store, items, label, include_ft=False):
    return SnapshotService(store, StaticCorpusSource(items)).snapshot(
        label=label, include_fulltext_hashes=include_ft).snapshot_id


def test_detects_added_study(tmp_path):
    store = store_with(tmp_path)
    a = snap(store, [ci("K1")], "a")
    b = snap(store, [ci("K1"), ci("K2", ck="jones2019", doi="10.1/y", pmid="222")], "b")
    rep = CorpusDiffService(store).diff(a, b)
    assert "jones2019" in rep.added and rep.removed == []


def test_detects_removed_study(tmp_path):
    store = store_with(tmp_path)
    a = snap(store, [ci("K1"), ci("K2", ck="jones2019", doi="10.1/y", pmid="222")], "a")
    b = snap(store, [ci("K1")], "b")
    rep = CorpusDiffService(store).diff(a, b)
    assert "jones2019" in rep.removed and rep.added == []


def test_detects_metadata_change(tmp_path):
    store = store_with(tmp_path)
    a = snap(store, [ci("K1", title="Old title")], "a")
    b = snap(store, [ci("K1", title="New title")], "b")
    rep = CorpusDiffService(store).diff(a, b)
    assert rep.changed and "metadata" in rep.changed[0].change_types
    assert "title_year" in rep.changed[0].change_types


def test_detects_doi_pmid_change(tmp_path):
    store = store_with(tmp_path)
    a = snap(store, [ci("K1", doi="10.1/x", pmid="111")], "a")
    b = snap(store, [ci("K1", doi="10.1/CHANGED", pmid="111")], "b")
    rep = CorpusDiffService(store).diff(a, b)
    assert "doi_pmid" in rep.changed[0].change_types


def test_detects_fulltext_hash_change(tmp_path):
    store = store_with(tmp_path)
    a = snap(store, [ci("K1", ft="h1")], "a", include_ft=True)
    b = snap(store, [ci("K1", ft="h2")], "b", include_ft=True)
    rep = CorpusDiffService(store).diff(a, b)
    assert "fulltext" in rep.changed[0].change_types


def test_citekey_change_with_same_identity_is_continuity(tmp_path):
    store = store_with(tmp_path)
    a = snap(store, [ci("K1", ck="old2020")], "a")
    b = snap(store, [ci("K1", ck="new2020")], "b")   # same item key + DOI/PMID
    rep = CorpusDiffService(store).diff(a, b)
    assert rep.added == [] and rep.removed == []      # treated as the same study


def _emap_with_links(store):
    svc = EvidenceMapService(store)
    emap = EvidenceMap()
    svc.add_node(emap, Node(node_id="s1", type="study",
                            item=ItemRef(zotero_key="K1", citekey="smith2020")))
    svc.add_node(emap, Node(node_id="o1", type="outcome", label="Mortality"))
    svc.add_link(emap, Link.model_validate({"from": "s1", "to": "o1", "type": "about_outcome"}))
    store.save_rating(make_grade_rating(rating_id="r1"))
    svc.add_attachment(emap, Attachment(attachment_id="a1", kind="assessment",
                                        scheme_kind="RoB2", study_node_id="s1", rating_id="r1"))
    svc.rebuild_reverse_index(emap)
    svc.save(emap)


def test_reports_affected_from_reverse_index(tmp_path):
    store = store_with(tmp_path)
    _emap_with_links(store)
    a = snap(store, [ci("K1", title="Old")], "a")
    b = snap(store, [ci("K1", title="New")], "b")
    rep = CorpusDiffService(store).diff(a, b)
    assert "smith2020" in rep.stale_candidates
    assert rep.affected.attachments == ["a1"]
    assert rep.affected.ratings == ["r1"]
    assert rep.affected.outcome_nodes == ["o1"]


def test_mark_stale_false_does_not_mutate(tmp_path):
    store = store_with(tmp_path)
    _emap_with_links(store)
    a = snap(store, [ci("K1", title="Old")], "a")
    b = snap(store, [ci("K1", title="New")], "b")
    before = len(store.load_evidence_map().attachments)
    CorpusDiffService(store).diff(a, b, mark_stale=False)
    assert len(store.load_evidence_map().attachments) == before


def test_mark_stale_true_adds_flag_and_audits(tmp_path):
    store = store_with(tmp_path)
    _emap_with_links(store)
    a = snap(store, [ci("K1", title="Old")], "a")
    b = snap(store, [ci("K1", title="New")], "b")
    rep = CorpusDiffService(store).diff(a, b, mark_stale=True)
    assert rep.stale_flags_added and rep.audit_event_id
    flags = [x for x in store.load_evidence_map().attachments if x.kind == "staleness_flag"]
    assert len(flags) == 1 and flags[0].citekey == "smith2020"
    assert store.audit.verify() is True


def test_compare_to_current_through_fake_seam(tmp_path):
    store = store_with(tmp_path)
    a = snap(store, [ci("K1", title="Old")], "a")
    current = StaticCorpusSource([ci("K1", title="New")])
    rep = CorpusDiffService(store, current).diff(a, compare_to_current=True)
    assert rep.to_snapshot_id == "current"
    assert rep.changed and "metadata" in rep.changed[0].change_types
