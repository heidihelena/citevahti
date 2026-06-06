"""Guarded write-back: dry-run default, confirmation tokens, honest degradation."""

from citevahti.intake import StaticLibraryIndex
from citevahti.schemas.common import GroupLibrary, ItemRef
from citevahti.state import CiteVahtiStore
from citevahti.writeback import FakeWriteBackend, UnavailableBackend, WritebackService


def _refs(keys):
    return [ItemRef(zotero_key=k) for k in keys]


def svc(tmp_path, backend=None, dedupe_index=None, tag_reader=None):
    store = CiteVahtiStore(tmp_path)
    store.init()
    backend = backend or FakeWriteBackend()
    s = WritebackService(store, backend, dedupe_index=dedupe_index, tag_reader=tag_reader)
    return s, store, backend


# ---- layer + token semantics ----------------------------------------------
def test_dry_run_default_and_writes_nothing(tmp_path):
    s, _, backend = svc(tmp_path)
    diff = s.tag_add(_refs(["K1"]), ["x"])          # dry_run defaults true
    assert diff.__class__.__name__ == "WriteDiff" and diff.dry_run is True
    assert backend.applied == []                    # nothing written


def test_dry_run_returns_preview_and_token(tmp_path):
    s, _, _ = svc(tmp_path)
    diff = s.tag_add(_refs(["K1"]), ["x"])
    assert diff.proposed_changes and diff.confirm_token


def test_confirmed_without_token_fails(tmp_path):
    s, _, backend = svc(tmp_path)
    res = s.tag_add(_refs(["K1"]), ["x"], dry_run=False)
    assert res.status == "failed" and res.error_code == "missing_confirm_token"
    assert backend.applied == []


def test_confirmed_with_wrong_token_fails(tmp_path):
    s, _, _ = svc(tmp_path)
    res = s.tag_add(_refs(["K1"]), ["x"], dry_run=False, confirm_token="bogus")
    assert res.error_code == "invalid_or_expired_token"


def test_token_invalid_if_payload_changes(tmp_path):
    s, _, _ = svc(tmp_path)
    diff = s.tag_add(_refs(["K1"]), ["a"])          # preview tags=[a]
    res = s.tag_add(_refs(["K1"]), ["b"], dry_run=False, confirm_token=diff.confirm_token)
    assert res.error_code == "payload_changed_token_invalid"


def test_token_is_one_use(tmp_path):
    s, _, _ = svc(tmp_path)
    diff = s.tag_add(_refs(["K1"]), ["x"])
    first = s.tag_add(_refs(["K1"]), ["x"], dry_run=False, confirm_token=diff.confirm_token)
    assert first.applied is True
    second = s.tag_add(_refs(["K1"]), ["x"], dry_run=False, confirm_token=diff.confirm_token)
    assert second.error_code == "invalid_or_expired_token"


def test_unavailable_backend_fails_cleanly_no_fallback(tmp_path):
    s, store, _ = svc(tmp_path, backend=UnavailableBackend(kind="local_addon"))
    diff = s.tag_add(_refs(["K1"]), ["x"])          # preview still works
    assert diff.confirm_token and diff.backend_available is False
    res = s.tag_add(_refs(["K1"]), ["x"], dry_run=False, confirm_token=diff.confirm_token)
    assert res.status == "unavailable" and res.error_code == "write_layer_unavailable"
    # no silent fallback -> nothing was applied/audited
    assert "zotero.write.applied" not in [e.event for e in store.audit.entries()]


def test_confirmed_write_audits_and_verifies(tmp_path):
    s, store, backend = svc(tmp_path)
    diff = s.tag_add(_refs(["K1"]), ["x"])
    res = s.tag_add(_refs(["K1"]), ["x"], dry_run=False, confirm_token=diff.confirm_token)
    assert res.applied and res.audit_event_id
    assert "zotero.write.applied" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


# ---- individual tools ------------------------------------------------------
def _confirm(fn, *args, **kw):
    diff = fn(*args, dry_run=True, **kw)
    return fn(*args, dry_run=False, confirm_token=diff.confirm_token, **kw)


def test_note_add_dry_run_and_confirmed(tmp_path):
    s, _, backend = svc(tmp_path)
    diff = s.note_add(ItemRef(zotero_key="K1"), "Title", "## body")
    assert "note" in diff.proposed_changes[0]
    res = _confirm(s.note_add, ItemRef(zotero_key="K1"), "Title", "## body")
    assert res.applied and backend.applied[0].kind == "note_add"


def test_annotation_add_dry_run(tmp_path):
    s, _, _ = svc(tmp_path)
    diff = s.annotation_add(ItemRef(zotero_key="ATT1"), page="12", text="quote")
    assert diff.kind == "annotation_add" and diff.dry_run is True


def test_item_add_dedupes_by_doi_pmid(tmp_path):
    s, _, _ = svc(tmp_path, dedupe_index=StaticLibraryIndex(dois=["10.1/x"]))
    diff = s.item_add({"DOI": "10.1/X", "title": "Dup"}, dedupe=True)
    assert diff.structured["create"] == [] and diff.structured["skipped"]
    assert "skip duplicate" in diff.proposed_changes[0]


def test_tag_add_and_remove(tmp_path):
    s, _, backend = svc(tmp_path)
    assert _confirm(s.tag_add, _refs(["K1"]), ["t"]).applied
    assert _confirm(s.tag_remove, _refs(["K1"]), ["t"]).applied
    assert {op.kind for op in backend.applied} == {"tag_add", "tag_remove"}


def test_collection_add_item(tmp_path):
    s, _, _ = svc(tmp_path)
    assert _confirm(s.collection_add_item, "COLL1", _refs(["K1", "K2"])).applied


def test_respects_library_selector(tmp_path):
    s, _, _ = svc(tmp_path)
    assert s.tag_add(_refs(["K1"]), ["t"], library="personal").library == "personal"
    grp = s.tag_add(_refs(["K1"]), ["t"], library=GroupLibrary(group_id="9"))
    assert "9" in grp.library


def test_no_evidence_map_mutation(tmp_path):
    s, store, _ = svc(tmp_path)
    before = store.load_evidence_map().model_dump()
    _confirm(s.tag_add, _refs(["K1"]), ["t"])
    _confirm(s.note_add, ItemRef(zotero_key="K1"), "T", "b")
    assert store.load_evidence_map().model_dump() == before
