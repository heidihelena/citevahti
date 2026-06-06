"""Contract test: Better BibTeX `item.search` returns CSL-JSON.

This pins the REAL response shape (recorded live) so the citekey resolver used by
map_bootstrap / extract / claim_check keeps working. Regression for the bug where
the resolver looked for an `itemKey` field that CSL-JSON doesn't have, treating
resolved citekeys as orphans.
"""

from citevahti.bbt.client import BbtClient
from citevahti.probe.client import HttpResponse
from citevahti.retrieval import ZoteroApiTextSource
from citevahti.retrieval.source import _extract_item_key
from citevahti.zotero import ZoteroService

from conftest import FakeHttpClient

# Exactly what api/json-rpc item.search returns (recorded from a live library).
CSL_ITEM = {
    "id": "http://zotero.org/users/424242/items/5H47Z9P9",
    "type": "article-journal",
    "citekey": "chaftAdjuvantNivolumabVs2026",
    "citation-key": "chaftAdjuvantNivolumabVs2026",
    "title": "Adjuvant Nivolumab vs Observation in Resected Non-Small Cell Lung Cancer",
    "DOI": "10.1001/jama.2026.8992",
    "container-title": "JAMA",
    "library": "My Library",
}


def _client():
    return FakeHttpClient({("POST", "json-rpc"): HttpResponse(
        200, _json={"jsonrpc": "2.0", "id": 1, "result": [CSL_ITEM]})})


def test_extract_item_key_from_csl_id_uri():
    assert _extract_item_key(CSL_ITEM) == "5H47Z9P9"
    # explicit key fields still win when present
    assert _extract_item_key({"key": "ABCD1234", "id": "http://.../items/ZZZ"}) == "ABCD1234"
    assert _extract_item_key({"id": "not-a-zotero-uri"}) is None


def test_resolver_resolves_real_citekey_to_item_ref():
    src = ZoteroApiTextSource(ZoteroService(_client()), BbtClient(_client()))
    ref = src.resolve_citekey("chaftAdjuvantNivolumabVs2026")
    assert ref is not None
    assert ref.zotero_key == "5H47Z9P9"
    assert ref.citekey == "chaftAdjuvantNivolumabVs2026"


def test_resolver_returns_none_on_citekey_mismatch():
    # item.search returned a different item -> not an exact citekey match
    src = ZoteroApiTextSource(ZoteroService(_client()), BbtClient(_client()))
    assert src.resolve_citekey("someone_elses_key_2020") is None


def test_bbt_existence_check_also_matches_csl():
    # bib_sync only needs existence; it matched on `citekey` (this kept working)
    assert BbtClient(_client()).resolve_citekey("chaftAdjuvantNivolumabVs2026") is True
    assert BbtClient(_client()).resolve_citekey("nope") is False
