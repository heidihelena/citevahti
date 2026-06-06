"""Connection & Capabilities report: tells the truth, leaks no secrets."""

from citevahti.capabilities import CapabilityStatusService
from citevahti.credentials import ZOTERO_WRITE_KEY
from citevahti.state import CiteVahtiStore

from conftest import FakeHttpClient
from citevahti.probe.client import HttpResponse, ProbeTransportError


def _store(tmp_path, mutate=None):
    s = CiteVahtiStore(tmp_path)
    if not s.exists():
        s.init()
    if mutate:
        cfg = s.load_config()
        mutate(cfg)
        s.save_config(cfg)
    return s


def _healthy():
    return FakeHttpClient({
        ("GET", "/api/"): HttpResponse(200, headers={"x-zotero-version": "9.0.4"}),
        ("POST", "json-rpc"): HttpResponse(200, _json={
            "jsonrpc": "2.0", "id": 1, "result": {"zotero": "9.0.4", "betterbibtex": "9.0.27"}}),
        ("GET", "cayw"): HttpResponse(200, text=""),
        ("GET", "groups"): HttpResponse(200, _json=[]),
    })


def _dead():
    return FakeHttpClient({
        ("GET", "/api/"): ProbeTransportError("refused"),
        ("POST", "json-rpc"): ProbeTransportError("refused"),
        ("GET", "cayw"): ProbeTransportError("refused"),
    })


def test_reports_live_connections_and_versions(tmp_path):
    rep = CapabilityStatusService(_store(tmp_path), _healthy()).report()
    assert rep.get("zotero_local_api").status == "connected"
    assert rep.get("zotero_local_api").version == "9.0.4"
    assert rep.get("better_bibtex").status == "connected"


def test_reports_unavailable_with_remediation(tmp_path):
    rep = CapabilityStatusService(_store(tmp_path), _dead()).report()
    z = rep.get("zotero_local_api")
    assert z.status == "unavailable" and z.remediation


def test_default_backend_can_create_nothing_live(tmp_path):
    # default config: writeback disabled -> UnavailableBackend
    rep = CapabilityStatusService(_store(tmp_path), _healthy()).report()
    assert rep.write_backend_available is False
    assert rep.supported_write_ops == []
    # all op kinds are honestly listed as not-writable
    assert "note_add" in rep.unsupported_write_ops and "item_add" in rep.unsupported_write_ops


def test_web_api_backend_lists_only_creation_as_writable(tmp_path, monkeypatch):
    monkeypatch.setenv("CITEVAHTI_ZOTERO_WRITE_KEY", "k")

    def enable(cfg):
        cfg.writeback.enabled = True
        cfg.writeback.kind = "web_api"
        cfg.zotero.user_id = "123"
        cfg.secrets_backend = "env"

    rep = CapabilityStatusService(_store(tmp_path, enable), _healthy()).report()
    assert rep.write_backend_available is True
    assert set(rep.supported_write_ops) == {"item_add", "intake_push"}
    assert "note_add" in rep.unsupported_write_ops
    assert rep.notes                                   # explains create-only limitation


def test_pubmed_email_state(tmp_path, monkeypatch):
    monkeypatch.delenv("NCBI_EMAIL", raising=False)

    def set_email(cfg):
        cfg.pubmed.contact_email = "x@y.org"

    rep = CapabilityStatusService(_store(tmp_path / "a", set_email), _healthy()).report()
    assert rep.get("pubmed_ncbi").status == "configured"
    rep2 = CapabilityStatusService(_store(tmp_path / "b"), _healthy()).report()
    assert rep2.get("pubmed_ncbi").status == "missing"


def test_secret_state_never_leaks_value(tmp_path, monkeypatch):
    monkeypatch.setenv("CITEVAHTI_ZOTERO_WRITE_KEY", "SUPER-SECRET-VALUE")

    def enable(cfg):
        cfg.secrets_backend = "env"

    rep = CapabilityStatusService(_store(tmp_path, enable), _healthy()).report()
    blob = rep.model_dump_json()
    assert "SUPER-SECRET-VALUE" not in blob
    wk = rep.get("zotero_write_key")
    assert wk.status == "configured"
    assert wk.secret_source == "env:CITEVAHTI_ZOTERO_WRITE_KEY"   # source, not value
