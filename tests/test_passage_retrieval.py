"""Deterministic passage retrieval: locators, hashes, degradation, library."""

from citevahti.bbt.client import BbtClient
from citevahti.probe.client import HttpResponse
from citevahti.retrieval import (
    AnnotationDoc,
    FullTextDoc,
    PassageRetrievalService,
    StaticTextSource,
    ZoteroApiTextSource,
)
from citevahti.schemas.common import GroupLibrary, ItemRef
from citevahti.util import sha256_hex
from citevahti.zotero import ZoteroService

from conftest import FakeHttpClient

FIXTURE = ("This was a multicenter, randomized, double-blind, placebo-controlled trial. "
           "We enrolled 480 patients with type 2 diabetes. "
           "The primary outcome was all-cause mortality at 5 years.")


def src(fulltext=None, annotations=None, items=None):
    return StaticTextSource(items=items or {},
                            fulltext=fulltext or {}, annotations=annotations or {})


def test_retrieves_passages_from_fixture_fulltext():
    s = src(fulltext={"K1": FullTextDoc(text=FIXTURE, attachment_key="ATT1")})
    r = PassageRetrievalService(s).retrieve(zotero_key="K1", query="mortality")
    assert r.status == "ok" and r.passages
    assert all(p.zotero_key == "K1" for p in r.passages)
    assert all(p.retrieval_method == "fulltext" for p in r.passages)


def test_preserves_citekey_itemkey_attachmentkey():
    s = src(fulltext={"K1": FullTextDoc(text=FIXTURE, attachment_key="ATT1")})
    ref = ItemRef(zotero_key="K1", citekey="smith2020")
    r = PassageRetrievalService(s).retrieve(item=ref)
    p = r.passages[0]
    assert p.citekey == "smith2020" and p.zotero_key == "K1" and p.attachment_key == "ATT1"


def test_preserves_page_and_location_from_annotation():
    s = src(fulltext={"K1": FullTextDoc(text="Some text about mortality.", attachment_key="ATT1")},
            annotations={"K1": [AnnotationDoc(key="A1", text="mortality was lower",
                                              page_label="12", page_index=11,
                                              attachment_key="ATT1")]})
    r = PassageRetrievalService(s).retrieve(zotero_key="K1", query="mortality")
    ann = [p for p in r.passages if p.retrieval_method == "annotation"]
    assert ann and ann[0].page == "12" and ann[0].location == "pageIndex:11"


def test_returns_text_hash():
    s = src(fulltext={"K1": FullTextDoc(text=FIXTURE)})
    r = PassageRetrievalService(s).retrieve(zotero_key="K1", query="mortality")
    p = r.passages[0]
    assert p.text_hash == sha256_hex(p.quote)


def test_degrades_when_fulltext_unavailable():
    s = src()  # nothing for K2
    r = PassageRetrievalService(s).retrieve(zotero_key="K2")
    assert r.status == "degraded" and r.error_code == "full_text_unavailable"
    assert r.remediation


def test_handles_annotation_only_item():
    s = src(annotations={"K1": [AnnotationDoc(key="A1", text="mortality lower", page_label="3")]})
    r = PassageRetrievalService(s).retrieve(zotero_key="K1", query="mortality")
    assert r.status == "ok"
    assert r.passages and r.passages[0].retrieval_method == "annotation"


def test_does_not_fabricate_locator():
    s = src(fulltext={"K1": FullTextDoc(text=FIXTURE)})
    r = PassageRetrievalService(s).retrieve(zotero_key="K1", query="mortality")
    # fulltext passages carry char locators but page is unknown -> null, not faked
    assert all(p.page is None for p in r.passages if p.retrieval_method == "fulltext")


def test_respects_library_selector_through_read_path():
    # exercises the live read seam: group library must hit groups/<id> URLs
    client = FakeHttpClient({
        ("GET", "children"): HttpResponse(200, _json=[
            {"key": "ATT1", "data": {"itemType": "attachment", "contentType": "application/pdf"}}]),
        ("GET", "fulltext"): HttpResponse(200, _json={"content": "mortality outcomes",
                                                      "indexedPages": 1}),
    })
    source = ZoteroApiTextSource(ZoteroService(client), BbtClient(client))
    r = PassageRetrievalService(source).retrieve(zotero_key="K1", query="mortality",
                                                 library=GroupLibrary(group_id="9"))
    assert r.status == "ok"
    assert any("groups/9/items/K1" in u for u in client.urls())
    assert any("groups/9/items/ATT1/fulltext" in u for u in client.urls())
