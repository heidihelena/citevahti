"""Read/discover zot_* (read-only): library selector + honest degradation."""

from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.schemas.common import GroupLibrary, ItemRef
from citevahti.zotero import ZoteroService

from conftest import FakeHttpClient

ITEMS = HttpResponse(200, _json=[
    {"key": "AAA", "data": {"itemType": "journalArticle", "title": "Trial A",
                            "date": "2020", "DOI": "10.1/x"}},
])


def test_search_personal_uses_users_base():
    client = FakeHttpClient({("GET", "/items"): ITEMS})
    res = ZoteroService(client).zot_search("trial", library="personal")
    assert res.ok and res.data[0]["title"] == "Trial A"
    assert any("users/0/items" in u for u in client.urls())  # personal -> users/0


def test_search_group_uses_group_base():
    client = FakeHttpClient({("GET", "/items"): ITEMS})
    res = ZoteroService(client).zot_search("trial", library=GroupLibrary(group_id="42"))
    assert res.ok
    assert any("groups/42/items" in u for u in client.urls())  # group -> groups/<id>


def test_search_passes_query_param():
    client = FakeHttpClient({("GET", "/items"): ITEMS})
    ZoteroService(client).zot_search("myeloma", library="personal")
    _, _, params = client.requests[0]
    assert params["q"] == "myeloma" and params["format"] == "json"


def test_bare_group_selector_is_rejected():
    client = FakeHttpClient({("GET", "/items"): ITEMS})
    res = ZoteroService(client).zot_search("x", library="group")
    assert not res.ok and res.error.code == "library_selector"


def test_zotero_absent_degrades_honestly():
    client = FakeHttpClient({("GET", "/items"): ProbeTransportError("refused")})
    res = ZoteroService(client).zot_search("x", library="personal")
    assert not res.ok
    assert res.error.code == "zotero_unavailable"
    assert "unreachable" in (res.error.remediation or "").lower()


def test_item_respects_ref_library():
    client = FakeHttpClient({("GET", "items/AAA"): HttpResponse(200, _json={
        "key": "AAA", "data": {"itemType": "book", "title": "Book Z"}})})
    ref = ItemRef(zotero_key="AAA", library=GroupLibrary(group_id="7"))
    res = ZoteroService(client).zot_item(ref)
    assert res.ok and res.data["title"] == "Book Z"
    assert any("groups/7/items/AAA" in u for u in client.urls())


def test_attachments_filters_to_attachment_type():
    children = HttpResponse(200, _json=[
        {"key": "N1", "data": {"itemType": "note"}},
        {"key": "P1", "data": {"itemType": "attachment", "title": "PDF",
                               "contentType": "application/pdf"}},
    ])
    client = FakeHttpClient({("GET", "children"): children})
    res = ZoteroService(client).zot_attachments(ItemRef(zotero_key="AAA"))
    assert res.ok and [a["key"] for a in res.data] == ["P1"]
