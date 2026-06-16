"""CiteVahti -> FullVahti tag write-back (the local_addon backend)."""

import json

import pytest

from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.schemas.config import Config
from citevahti.schemas.writeback import WriteOperation
from citevahti.writeback.backend import UnavailableBackend, WriteUnavailable, make_backend
from citevahti.writeback.local_addon import FullVahtiWriteBackend, is_loopback


class _FakeHttp:
    """Records POSTs; returns scripted responses for get/post."""

    def __init__(self, ping=None, post_status=200, post_text=""):
        self.posts = []
        self._ping = ping
        self._post_status = post_status
        self._post_text = post_text
        self.raise_on_post = False

    def get(self, url, headers=None, params=None):
        if self._ping is None:
            raise ProbeTransportError("refused")
        return HttpResponse(status_code=200, text=json.dumps(self._ping))

    def post(self, url, json=None, headers=None):
        if self.raise_on_post:
            raise ProbeTransportError("refused")
        self.posts.append(json)
        return HttpResponse(status_code=self._post_status, text=self._post_text)


def _backend(http, **kw):
    return FullVahtiWriteBackend(http, token="tok-secret", **kw)


# ---- the door contract ------------------------------------------------------
def test_tag_add_posts_the_fullvahti_payload():
    http = _FakeHttp()
    b = _backend(http)
    op = WriteOperation(kind="tag_add", targets=["ITEMKEY1"],
                        structured={"add_tags": ["fulltext:open"], "targets": ["ITEMKEY1"]})
    res = b.apply(op)
    assert res["backend"] == "local_addon" and res["targets"] == ["ITEMKEY1"]
    assert http.posts == [{"token": "tok-secret", "itemKey": "ITEMKEY1",
                           "add": ["fulltext:open"], "remove": []}]


def test_tag_remove_posts_remove():
    http = _FakeHttp()
    _backend(http).apply(WriteOperation(kind="tag_remove", targets=["K"],
                                        structured={"remove_tags": ["cite:closer-look"]}))
    assert http.posts[0]["remove"] == ["cite:closer-look"] and http.posts[0]["add"] == []


def test_tag_mirror_uses_per_target_add_remove():
    http = _FakeHttp()
    op = WriteOperation(kind="tag_mirror", targets=["K1"],
                        structured={"per_target": [{"zotero_key": "K1", "add": ["g:moderate"],
                                                     "remove": ["g:low"]}], "new_tag": "g:moderate"})
    _backend(http).apply(op)
    assert http.posts[0] == {"token": "tok-secret", "itemKey": "K1",
                             "add": ["g:moderate"], "remove": ["g:low"]}


def test_only_tag_kinds_supported():
    b = _backend(_FakeHttp())
    assert b.supports("tag_add") and b.supports("tag_remove") and b.supports("tag_mirror")
    assert not b.supports("item_add") and not b.supports("intake_push")
    with pytest.raises(WriteUnavailable):
        b.apply(WriteOperation(kind="item_add", targets=["K"]))


def test_non_200_is_a_clean_write_error():
    b = _backend(_FakeHttp(post_status=403, post_text="bad token"))
    with pytest.raises(WriteUnavailable):
        b.apply(WriteOperation(kind="tag_add", targets=["K"], structured={"add_tags": ["x"]}))


def test_unreachable_door_is_a_clean_error():
    http = _FakeHttp(); http.raise_on_post = True
    with pytest.raises(WriteUnavailable):
        _backend(http).apply(WriteOperation(kind="tag_add", targets=["K"],
                                            structured={"add_tags": ["x"]}))


def test_undo_swaps_add_and_remove():
    http = _FakeHttp()
    b = _backend(http)
    res = b.apply(WriteOperation(kind="tag_add", targets=["K"], structured={"add_tags": ["t"]}))
    http.posts.clear()
    b.undo({"applied": res["applied"]})
    assert http.posts[0]["remove"] == ["t"] and http.posts[0]["add"] == []


def test_ping_reports_writeback_state():
    b = _backend(_FakeHttp(ping={"version": "0.1", "writeback": True}))
    p = b.ping()
    assert p["reachable"] is True and p["writeback"] is True and p["version"] == "0.1"


# ---- the token is local-only ------------------------------------------------
def test_refuses_non_loopback_without_optin():
    assert is_loopback("http://127.0.0.1:23119") and not is_loopback("http://example.com")
    with pytest.raises(WriteUnavailable):
        _backend(_FakeHttp(), base="http://example.com:23119")
    # explicit opt-in allows it
    _backend(_FakeHttp(), base="http://example.com:23119", allow_remote=True)


# ---- make_backend selects it ------------------------------------------------
def test_make_backend_local_addon_needs_a_token(monkeypatch):
    monkeypatch.delenv("CITEVAHTI_FULLVAHTI_TOKEN", raising=False)
    cfg = Config.default()
    cfg.writeback.enabled = True
    cfg.writeback.kind = "local_addon"
    b = make_backend(cfg)
    assert isinstance(b, UnavailableBackend) and "FullVahti" in b.reason


def test_make_backend_local_addon_with_token(monkeypatch):
    monkeypatch.setenv("CITEVAHTI_FULLVAHTI_TOKEN", "tok-xyz")
    cfg = Config.default()
    cfg.writeback.enabled = True
    cfg.writeback.kind = "local_addon"
    b = make_backend(cfg)
    assert isinstance(b, FullVahtiWriteBackend) and b.supports("tag_add")
