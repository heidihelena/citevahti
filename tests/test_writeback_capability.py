"""Capability-honest write-back: previews don't lie, and failed writes are audited.

Regressions for the AI-writer findings: note/tag previews "succeeded" then the
confirmed write failed (capability/preview mismatch), and failed write attempts
left no audit trace.
"""

from citevahti.probe.client import HttpResponse
from citevahti.schemas.common import ItemRef
from citevahti.state import CiteVahtiStore
from citevahti.writeback import WritebackService
from citevahti.writeback.backend import ALL_WRITE_KINDS, UnavailableBackend
from citevahti.writeback.webapi import WebApiWriteBackend


class _Http:
    def get(self, *a, **k):
        raise AssertionError("no GET")

    def post(self, url, json=None, headers=None):
        return HttpResponse(200, _json={"successful": {"0": {"key": "K"}}, "failed": {}})


def _store(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    return s


def _web_svc(tmp_path):
    return WritebackService(_store(tmp_path), WebApiWriteBackend(_Http(), "key", "123"))


# ---- backend.supports ------------------------------------------------------
def test_web_api_supports_only_creation():
    be = WebApiWriteBackend(_Http(), "k", "1")
    assert be.supports("item_add") and be.supports("intake_push")
    assert not be.supports("note_add") and not be.supports("tag_add")
    assert UnavailableBackend().supports("item_add") is False


# ---- preview fails EARLY on an unsupported op ------------------------------
def test_preview_unsupported_op_yields_no_token(tmp_path):
    svc = _web_svc(tmp_path)
    diff = svc.tag_add([ItemRef(zotero_key="AAAA1111")], ["mytag"], dry_run=True)
    assert diff.status == "unsupported"
    assert diff.backend_supports_kind is False
    assert diff.confirm_token == ""                       # nothing to confirm
    assert diff.error_code == "operation_unsupported"
    assert any("not supported" in w for w in diff.warnings)


def test_preview_supported_op_still_works(tmp_path):
    # item creation IS supported by web_api -> a real token is minted
    svc = _web_svc(tmp_path)
    diff = svc.item_add({"title": "T", "doi": "10.1/x"}, dry_run=True)
    assert diff.status == "preview" and diff.backend_supports_kind is True
    assert diff.confirm_token


# ---- a confirmed unsupported write fails AND is audited --------------------
def test_confirmed_unsupported_write_is_audited(tmp_path):
    store = _store(tmp_path)
    svc = WritebackService(store, WebApiWriteBackend(_Http(), "key", "123"))
    # force past the token gate with a layer that doesn't require a token
    svc.layer.confirm_required = False
    res = svc.tag_add([ItemRef(zotero_key="AAAA1111")], ["t"], dry_run=False)
    assert res.applied is False and res.error_code == "operation_unsupported"
    events = [e.event for e in store.audit.entries()]
    assert "zotero.write.failed" in events
    assert store.audit.verify() is True


# ---- a confirmed write to an unavailable backend is also audited -----------
def test_confirmed_write_to_unavailable_backend_is_audited(tmp_path):
    store = _store(tmp_path)
    svc = WritebackService(store, UnavailableBackend())
    svc.layer.confirm_required = False
    res = svc.item_add({"title": "T"}, dry_run=False)
    assert res.applied is False and res.error_code == "write_layer_unavailable"
    assert "zotero.write.failed" in [e.event for e in store.audit.entries()]
    assert res.audit_event_id is not None


def test_all_write_kinds_constant_covers_the_tool_surface():
    for k in ("item_add", "intake_push", "note_add", "annotation_add",
              "tag_add", "tag_remove", "collection_add_item", "tag_mirror"):
        assert k in ALL_WRITE_KINDS
