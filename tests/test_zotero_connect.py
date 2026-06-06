"""Guided one-paste Zotero connection (ADR-0005).

Reads stay keyless; this validates a pasted key, learns the userID, stores the key
in the credential store (never config), and enables the guarded web_api backend.
The key is never echoed back.
"""

import pytest

from citevahti.credentials import ZOTERO_WRITE_KEY, InMemoryCredentialStore
from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.state import CiteVahtiStore
from citevahti.zotero import ZoteroConnectError, ZoteroConnectService, new_key_url

KEY = "AbCdEf0123456789xyz"


class FakeHttp:
    def __init__(self, response=None, raise_transport=False):
        self.response = response
        self.raise_transport = raise_transport
        self.calls = []

    def get(self, url, headers=None, params=None):
        self.calls.append((url, headers or {}))
        if self.raise_transport:
            raise ProbeTransportError("connection refused")
        return self.response


def _keys_response(write=True, user_id=424242, username="researcher", status=200):
    body = {"key": "redacted", "userID": user_id, "username": username,
            "access": {"user": {"library": True, "files": True, "notes": True, "write": write}}}
    return HttpResponse(status_code=status, _json=body)


def _store(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    return s


def _svc(store, http):
    return ZoteroConnectService(store, http=http, credential_store=InMemoryCredentialStore())


def test_new_key_url_prefills_name_and_write():
    url = new_key_url("CiteVahti")
    assert url.startswith("https://www.zotero.org/settings/keys/new?")
    assert "name=CiteVahti" in url
    assert "write_access=1" in url and "library_access=1" in url
    assert "all_groups" not in url                            # personal-only by default


def test_new_key_url_can_prefill_group_access():
    assert "all_groups=write" in new_key_url("CiteVahti", groups="write")
    assert "all_groups=read" in new_key_url("CiteVahti", groups="read")
    assert "all_groups" not in new_key_url("CiteVahti", groups="none")


def test_connect_reports_personal_and_group_access(tmp_path):
    store = _store(tmp_path)
    # a key with personal write + one writable group + one read-only group
    body = {"userID": 424242, "username": "researcher",
            "access": {"user": {"library": True, "write": True},
                       "groups": {"111": {"library": True, "write": True},
                                  "222": {"library": True, "write": False}}}}
    rep = _svc(store, FakeHttp(HttpResponse(status_code=200, _json=body))).connect(KEY)
    assert rep["personal_write"] is True
    assert rep["groups_total"] == 2 and rep["groups_write"] == 1


def test_connect_stores_key_learns_userid_and_enables_web_api(tmp_path):
    store = _store(tmp_path)
    svc = _svc(store, FakeHttp(_keys_response(write=True)))
    rep = svc.connect(KEY)

    assert rep["connected"] is True and rep["user_id"] == "424242"
    assert rep["write_access"] is True
    assert KEY not in repr(rep)                              # never echoes the key
    # key landed in the credential store, not config
    assert svc._cred.get_secret(ZOTERO_WRITE_KEY) == KEY
    cfg = store.load_config()
    assert cfg.zotero.user_id == "424242"
    assert cfg.writeback.web_api_user_id == "424242"
    assert cfg.writeback.enabled is True and cfg.writeback.kind == "web_api"
    assert KEY not in cfg.model_dump_json()                 # key never in config


def test_connect_sends_the_key_in_the_header_not_the_url(tmp_path):
    store = _store(tmp_path)
    http = FakeHttp(_keys_response())
    _svc(store, http).connect(KEY)
    url, headers = http.calls[0]
    assert url.endswith("/keys/current") and KEY not in url
    assert headers.get("Zotero-API-Key") == KEY


def test_invalid_key_is_refused_and_nothing_is_stored(tmp_path):
    store = _store(tmp_path)
    svc = _svc(store, FakeHttp(_keys_response(status=403)))
    with pytest.raises(ZoteroConnectError) as ei:
        svc.connect(KEY)
    assert ei.value.code == "invalid_key"
    assert svc._cred.get_secret(ZOTERO_WRITE_KEY) is None
    assert store.load_config().writeback.enabled is False


def test_read_only_key_is_refused_by_default(tmp_path):
    store = _store(tmp_path)
    svc = _svc(store, FakeHttp(_keys_response(write=False)))
    with pytest.raises(ZoteroConnectError) as ei:
        svc.connect(KEY)
    assert ei.value.code == "no_write_access"
    assert svc._cred.get_secret(ZOTERO_WRITE_KEY) is None    # not stored
    assert store.load_config().writeback.enabled is False


def test_unreachable_api_degrades_honestly(tmp_path):
    store = _store(tmp_path)
    svc = _svc(store, FakeHttp(raise_transport=True))
    with pytest.raises(ZoteroConnectError) as ei:
        svc.connect(KEY)
    assert ei.value.code == "api_unreachable"


def test_empty_key_refused(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ZoteroConnectError) as ei:
        _svc(store, FakeHttp(_keys_response())).connect("   ")
    assert ei.value.code == "empty_key"


def test_tool_facade_connect(tmp_path):
    from citevahti import tools
    CiteVahtiStore(tmp_path).init()
    rep = tools.connect_zotero(KEY, root=str(tmp_path),
                               http=FakeHttp(_keys_response()),
                               credential_store=InMemoryCredentialStore())
    assert rep["user_id"] == "424242" and rep["write_access"] is True


def test_cli_connect_zotero_success(tmp_path, capsys, monkeypatch):
    from citevahti import tools
    from citevahti.cli import main
    CiteVahtiStore(tmp_path).init()
    monkeypatch.setattr(tools, "connect_zotero", lambda *a, **k: {
        "connected": True, "user_id": "424242", "username": "researcher",
        "write_access": True, "secrets_backend": "memory", "note": "ok"})
    rc = main(["--root", str(tmp_path), "connect-zotero", "--no-open", "--key", KEY])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Connected to Zotero as researcher" in out
    assert KEY not in out                                    # the pasted key is never echoed
    assert "keys/new?" in out                                # showed the pre-filled URL
