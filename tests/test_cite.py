"""cite: resolves via BBT, fails on unresolved keys, never invents, degrades honestly."""

from citevahti.cite import CiteService
from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.probe.probe import CapabilityReport, ProbeResult
from citevahti.schemas.common import ItemRef

from conftest import FakeHttpClient


def _bbt(result):
    return FakeHttpClient({("POST", "json-rpc"): HttpResponse(200, _json={
        "jsonrpc": "2.0", "id": 1, "result": result})})


def test_successful_fixture_citekey_resolution():
    client = _bbt([{"citekey": "smith2020", "title": "Smith 2020"}])
    res = CiteService(client).cite("smith2020", format="pandoc")
    assert res.ok
    assert res.data["citation"] == "[@smith2020]"
    assert res.data["citekey"] == "smith2020"


def test_unresolved_citekey_fails_and_does_not_invent():
    client = _bbt([])  # BBT knows nothing matching
    res = CiteService(client).cite("ghost1999")
    assert not res.ok
    assert res.error.code == "unresolved_citekey"
    assert "never invents" in res.error.message


def test_near_match_is_not_accepted():
    # a different item is returned but no exact citekey match -> unresolved
    client = _bbt([{"citekey": "smith2021"}])
    res = CiteService(client).cite("smith2020")
    assert not res.ok and res.error.code == "unresolved_citekey"


def test_itemref_without_citekey_is_rejected():
    # never invents a key from a bare item reference
    client = _bbt([{"citekey": "whatever"}])
    res = CiteService(client).cite(ItemRef(zotero_key="AAA"))
    assert not res.ok and res.error.code == "no_citekey"


def test_itemref_with_citekey_resolves():
    client = _bbt([{"citekey": "smith2020"}])
    res = CiteService(client).cite(ItemRef(zotero_key="AAA", citekey="smith2020"))
    assert res.ok and res.data["citation"] == "[@smith2020]"


def test_bbt_absent_degrades_honestly():
    client = FakeHttpClient({("POST", "json-rpc"): ProbeTransportError("refused")})
    res = CiteService(client).cite("smith2020")
    assert not res.ok
    assert res.error.code == "bbt_unavailable"
    assert "Better BibTeX" in (res.error.remediation or "")


def test_capability_gate_blocks_before_call():
    # when a probe says BBT is down, cite fails without even calling
    report = CapabilityReport(results={"bbt_ready": ProbeResult("bbt_ready", False, "down")})
    client = _bbt([{"citekey": "smith2020"}])
    res = CiteService(client, capability=report).cite("smith2020")
    assert not res.ok and res.error.code == "bbt_unavailable"
    assert client.requests == []  # never reached out


def test_pandoc_and_latex_formats():
    client = _bbt([{"citekey": "smith2020"}])
    assert CiteService(client).cite("smith2020", "latex").data["citation"] == "\\cite{smith2020}"
