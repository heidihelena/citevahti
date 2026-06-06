"""snapshot: hashes, probe summaries, citekey coverage, honest degradation."""

from citevahti.corpus import CorpusItem, SnapshotService, StaticCorpusSource
from citevahti.state import CiteVahtiStore


def item(zk="K1", ck="smith2020", **kw):
    base = dict(zotero_key=zk, citekey=ck, title="A study", doi="10.1/x", pmid="111",
                year=2020, fulltext_hash="ftH")
    base.update(kw)
    return CorpusItem(**base)


def svc(tmp_path, source):
    store = CiteVahtiStore(tmp_path)
    store.init()
    return SnapshotService(store, source), store


def test_writes_snapshot_file(tmp_path):
    s, store = svc(tmp_path, StaticCorpusSource([item()]))
    rec = s.snapshot(label="baseline")
    assert rec.status == "ok" and store.list_snapshots() == [rec.snapshot_id]


def test_includes_probe_summaries_and_library(tmp_path):
    s, _ = svc(tmp_path, StaticCorpusSource([item()]))
    rec = s.snapshot(library="personal")
    assert rec.zotero_probe.version == "9.0.4" and rec.bbt_probe.version == "9.0.27"
    assert rec.library == "personal"


def test_stores_item_key_and_citekey(tmp_path):
    s, _ = svc(tmp_path, StaticCorpusSource([item()]))
    rec = s.snapshot()
    assert "smith2020" in rec.items                    # keyed by citekey
    assert rec.items["smith2020"].zotero_key == "K1"
    assert rec.items["smith2020"].metadata_hash


def test_does_not_invent_citekey_when_bbt_unresolved(tmp_path):
    s, _ = svc(tmp_path, StaticCorpusSource([item()], bbt_available=False))
    rec = s.snapshot()
    assert "K1" in rec.items                            # keyed by item key, not faked citekey
    assert rec.items["K1"].citekey is None
    assert rec.citekey_coverage == "degraded"
    assert rec.status == "ok"                           # still snapshots


def test_fulltext_hash_only_when_requested(tmp_path):
    s, _ = svc(tmp_path, StaticCorpusSource([item()]))
    assert s.snapshot(include_fulltext_hashes=False).items["smith2020"].fulltext_hash is None
    s2, _ = svc(tmp_path / "b", StaticCorpusSource([item()]))
    assert s2.snapshot(include_fulltext_hashes=True).items["smith2020"].fulltext_hash == "ftH"


def test_zotero_unavailable_no_fake_snapshot(tmp_path):
    s, store = svc(tmp_path, StaticCorpusSource([item()], zotero_available=False))
    rec = s.snapshot()
    assert rec.status == "degraded" and rec.error_code == "zotero_unavailable"
    assert store.list_snapshots() == []                # nothing written


def test_audit_event_and_verify(tmp_path):
    s, store = svc(tmp_path, StaticCorpusSource([item()]))
    rec = s.snapshot()
    assert rec.audit_event_id is not None
    assert "snapshot.write" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True
