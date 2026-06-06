"""Zotero Web API write backend: item creation + collection assignment, offline.

No real network: a fake HTTP client captures the POST. Verifies the guarded
flow (dry-run token -> confirmed write -> audit) and that unsupported operations
and missing credentials degrade honestly with no silent fallback.
"""

import pytest

from citevahti.probe.client import HttpResponse
from citevahti.schemas.common import Provenance
from citevahti.schemas.config import Config
from citevahti.schemas.intake import IntakeHit, IntakeRecord
from citevahti.schemas.writeback import WriteOperation
from citevahti.state import CiteVahtiStore
from citevahti.writeback import (
    UnavailableBackend,
    WebApiWriteBackend,
    WritebackService,
    make_backend,
)
from citevahti.writeback.backend import WriteUnavailable


class FakeZoteroHttp:
    def __init__(self, response, existing=None):
        self.response = response
        self.posts = []
        self.gets = []
        self._existing = existing if existing is not None else []   # find_existing search hits

    def get(self, url, headers=None, params=None):
        # item creation is POST-only; the only GET is the find_existing dedupe
        # re-check, which returns the seeded (empty by default) search result.
        self.gets.append({"url": url, "params": params})
        return HttpResponse(200, _json=self._existing)

    def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers or {}})
        return self.response


def ok_response(keys):
    return HttpResponse(200, _json={"successful": {str(i): {"key": k} for i, k in enumerate(keys)},
                                    "failed": {}})


def intake_op(collection_key="T7XK7MJH"):
    return WriteOperation(
        kind="intake_push", library="personal", targets=[],
        payload={"batch_id": "b1", "collection_key": collection_key, "create_ids": ["pmid:111"]},
        structured={"create": [{"record_id": "pmid:111", "doi": "10.1/x", "pmid": "111",
                                "title": "P-values misused", "authors": ["Jane Doe", "WHO"],
                                "journal": "J Test", "year": 2024, "publication_date": "2024-03"}],
                    "skipped": [], "collection_key": collection_key})


# ---- backend unit ----------------------------------------------------------
def test_creates_items_with_collection_and_auth_header():
    http = FakeZoteroHttp(ok_response(["AAAA1111"]))
    backend = WebApiWriteBackend(http, api_key="SECRET", user_id="12345")
    result = backend.apply(intake_op("T7XK7MJH"))
    assert result["created_keys"] == ["AAAA1111"] and result["created"] == 1
    post = http.posts[0]
    assert post["url"] == "https://api.zotero.org/users/12345/items"
    assert post["headers"]["Zotero-API-Key"] == "SECRET"
    assert post["headers"]["Zotero-API-Version"] == "3"
    item = post["json"][0]
    assert item["itemType"] == "journalArticle"
    assert item["DOI"] == "10.1/x" and "PMID: 111" in item["extra"]
    assert item["collections"] == ["T7XK7MJH"]            # assigned at creation
    # creators parsed: "Jane Doe" -> first/last, "WHO" -> single-field name
    assert {"creatorType": "author", "firstName": "Jane", "lastName": "Doe"} in item["creators"]
    assert {"creatorType": "author", "name": "WHO"} in item["creators"]


def test_no_collection_when_not_requested():
    http = FakeZoteroHttp(ok_response(["K1"]))
    op = intake_op(collection_key=None)
    WebApiWriteBackend(http, "k", "1").apply(op)
    assert "collections" not in http.posts[0]["json"][0]


def test_unsupported_operation_raises_unavailable():
    backend = WebApiWriteBackend(FakeZoteroHttp(ok_response([])), "k", "1")
    op = WriteOperation(kind="tag_add", library="personal", targets=["K1"],
                        payload={"tags": ["x"]}, structured={"add_tags": ["x"], "targets": ["K1"]})
    with pytest.raises(WriteUnavailable):
        backend.apply(op)


def test_http_error_raises_unavailable():
    backend = WebApiWriteBackend(FakeZoteroHttp(HttpResponse(403, text="forbidden")), "k", "1")
    with pytest.raises(WriteUnavailable):
        backend.apply(intake_op())


# ---- make_backend selection (no silent fallback) ---------------------------
def _web_cfg():
    cfg = Config.default()
    cfg.writeback.enabled = True
    cfg.writeback.kind = "web_api"
    cfg.zotero.user_id = "12345"
    cfg.secrets_backend = "env"   # keep tests off the real OS keychain
    return cfg


def test_make_backend_web_api_with_creds(monkeypatch):
    monkeypatch.setenv("CITEVAHTI_ZOTERO_WRITE_KEY", "k")   # env escape hatch
    backend = make_backend(_web_cfg())
    assert isinstance(backend, WebApiWriteBackend) and backend.available is True
    assert backend.user_id == "12345"


def test_make_backend_web_api_missing_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("CITEVAHTI_ZOTERO_WRITE_KEY", raising=False)
    backend = make_backend(_web_cfg())
    assert isinstance(backend, UnavailableBackend) and backend.available is False
    assert "missing credentials" in backend.reason


def test_make_backend_disabled_is_unavailable():
    assert isinstance(make_backend(Config.default()), UnavailableBackend)


# ---- integration through the guarded WriteLayer ----------------------------
def _store_with_intake(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    rec = IntakeRecord(
        batch_id="b1", provider="pubmed", exact_query="p value misuse lung cancer",
        run_at="2026-06-02T00:00:00+00:00",
        provenance=Provenance(tool="literature_search", tool_version="0.1.1",
                              ran_at="2026-06-02T00:00:00+00:00", config_hash="h"),
        hits=[IntakeHit(record_id="pmid:111", pmid="111", doi="10.1/x", title="P-values misused",
                        authors=["Jane Doe"], journal="J Test", year=2024,
                        publication_date="2024-03", dedupe_status="new")])
    store.save_intake(rec)
    return store


def test_dry_run_then_confirmed_write_creates_and_audits(tmp_path):
    store = _store_with_intake(tmp_path)
    http = FakeZoteroHttp(ok_response(["AAAA1111"]))
    svc = WritebackService(store, WebApiWriteBackend(http, "SECRET", "12345"))

    diff = svc.intake_push("b1", collection_key="T7XK7MJH", dry_run=True)
    assert diff.dry_run is True and diff.backend_available is True and diff.confirm_token
    assert len(http.posts) == 0                       # dry-run wrote nothing

    res = svc.intake_push("b1", collection_key="T7XK7MJH", dry_run=False,
                          confirm_token=diff.confirm_token)
    assert res.applied is True and res.status == "applied"
    assert res.result["created_keys"] == ["AAAA1111"]
    assert len(http.posts) == 1                       # confirmed write happened
    assert "zotero.write.applied" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


def test_confirmed_write_requires_valid_token(tmp_path):
    store = _store_with_intake(tmp_path)
    svc = WritebackService(store, WebApiWriteBackend(FakeZoteroHttp(ok_response(["K"])), "k", "1"))
    res = svc.intake_push("b1", collection_key="T7XK7MJH", dry_run=False, confirm_token="bogus")
    assert res.applied is False and res.error_code == "invalid_or_expired_token"
