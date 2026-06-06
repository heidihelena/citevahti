"""Zotero version parsing: real version, or null+unknown -- never a placeholder."""

import pytest

from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.probe.probe import probe_bbt_ready, probe_zotero_api
from citevahti.schemas.config import Endpoints
from citevahti.util import looks_like_version
from citevahti.validators.errors import ValidationError
from citevahti.validators.probe import assert_valid_probed_version

from conftest import FakeHttpClient

EP = Endpoints()


def _client(resp):
    return FakeHttpClient({("GET", "/api/"): resp})


def _bbt_client(resp):
    return FakeHttpClient({("POST", "json-rpc"): resp})


def test_version_parsed_from_header():
    r = probe_zotero_api(_client(HttpResponse(200, headers={"zotero-version": "9.0.4"})), EP)
    assert r.available is True
    assert r.version == "9.0.4"
    assert r.version_status == "parsed"
    assert r.remediation is None


def test_version_parsed_from_json_body():
    r = probe_zotero_api(_client(HttpResponse(200, _json={"version": "9.1.0"})), EP)
    assert r.version == "9.1.0" and r.version_status == "parsed"


def test_schema_version_integer_is_not_an_app_version():
    # The live failure: only the integer schema version is present.
    resp = HttpResponse(200, headers={"zotero-schema-version": "42"})
    r = probe_zotero_api(_client(resp), EP)
    assert r.available is True          # reachable
    assert r.version is None            # never a fake version
    assert r.version_status == "unknown"
    assert "could not be parsed" in (r.remediation or "")


def test_bare_integer_in_version_header_is_rejected():
    r = probe_zotero_api(_client(HttpResponse(200, headers={"zotero-version": "42"})), EP)
    assert r.version is None and r.version_status == "unknown"


def test_unreachable_has_no_version():
    r = probe_zotero_api(_client(ProbeTransportError("refused")), EP)
    assert r.available is False
    assert r.version is None
    assert r.version_status is None


def test_looks_like_version():
    assert looks_like_version("9.0.4") and looks_like_version("9.0")
    assert not looks_like_version("42")
    assert not looks_like_version("v9.0.4")
    assert not looks_like_version("")
    assert not looks_like_version(None)


def test_validator_rejects_placeholder_accepts_version_or_null():
    assert_valid_probed_version("9.0.4")
    assert_valid_probed_version(None)
    with pytest.raises(ValidationError):
        assert_valid_probed_version("42")


def test_app_version_read_from_x_zotero_version_header():
    # the live server exposes the APP version via x-zotero-version, alongside
    # the schema version (42) and local-api version (3) which must be ignored.
    resp = HttpResponse(200, text="Nothing to see here.", headers={
        "x-zotero-version": "9.0.3",
        "zotero-schema-version": "42",
        "zotero-api-version": "3",
    })
    r = probe_zotero_api(_client(resp), EP)
    assert r.version == "9.0.3" and r.version_status == "parsed"


# ---- Better BibTeX version (distinct from app/schema versions) ------------
def test_bbt_ready_without_version_reports_unknown_not_fake():
    # api.ready=true but no BBT version exposed -> ready true, version unknown
    resp = HttpResponse(200, _json={"jsonrpc": "2.0", "id": 1, "result": True})
    r = probe_bbt_ready(_bbt_client(resp), EP)
    assert r.available is True
    assert r.version is None
    assert r.version_status == "unknown"


def test_bbt_version_not_taken_from_app_version_header():
    # x-zotero-version is the APP version; it must NOT become the BBT version
    resp = HttpResponse(200, headers={"x-zotero-version": "9.0.3"},
                        _json={"jsonrpc": "2.0", "id": 1, "result": True})
    r = probe_bbt_ready(_bbt_client(resp), EP)
    assert r.available is True
    assert r.version is None and r.version_status == "unknown"


def test_bbt_version_parsed_when_exposed():
    resp = HttpResponse(200, headers={"x-better-bibtex-version": "9.0.27"},
                        _json={"jsonrpc": "2.0", "id": 1, "result": True})
    r = probe_bbt_ready(_bbt_client(resp), EP)
    assert r.version == "9.0.27" and r.version_status == "parsed"


def test_bbt_down_has_no_version():
    resp = HttpResponse(404, text="No endpoint found")
    r = probe_bbt_ready(_bbt_client(resp), EP)
    assert r.available is False and r.version is None


def test_bbt_ready_dict_response_parses_betterbibtex_version():
    # real BBT shape: api.ready returns {"zotero": "<app>", "betterbibtex": "<bbt>"}
    resp = HttpResponse(200, _json={"jsonrpc": "2.0", "id": 1,
                                    "result": {"zotero": "9.0.4", "betterbibtex": "9.0.27"}})
    r = probe_bbt_ready(_bbt_client(resp), EP)
    assert r.available is True
    assert r.version == "9.0.27" and r.version_status == "parsed"


def test_bbt_dict_response_does_not_use_zotero_field_as_bbt_version():
    # the app version in the "zotero" field must never become the BBT version
    resp = HttpResponse(200, _json={"jsonrpc": "2.0", "id": 1,
                                    "result": {"zotero": "9.0.4"}})
    r = probe_bbt_ready(_bbt_client(resp), EP)
    assert r.available is True
    assert r.version is None and r.version_status == "unknown"
