"""claim_check: candidate-only statuses, per-citekey + aggregate, never asserts truth."""

from citevahti.claimcheck import ClaimCheckService
from citevahti.retrieval import FullTextDoc, StaticTextSource
from citevahti.schemas.common import ItemRef

FIXTURE = (
    "This was a randomized controlled trial. "
    "The primary outcome was all-cause mortality at 5 years. "
    "The hazard ratio was 0.78."
)


def source():
    return StaticTextSource(
        items={"smith2020": ItemRef(zotero_key="K1", citekey="smith2020"),
               "jones2019": ItemRef(zotero_key="K2", citekey="jones2019"),
               "nofulltext": ItemRef(zotero_key="K3", citekey="nofulltext")},
        fulltext={"K1": FullTextDoc(text=FIXTURE, attachment_key="ATT1"),
                  "K2": FullTextDoc(text="An unrelated paper about agriculture.")},
    )


def svc():
    return ClaimCheckService(source())


def test_supported_candidate_when_passage_exists():
    r = svc().check("primary outcome all-cause mortality", ["smith2020"])
    pc = r.per_citekey[0]
    assert pc.status == "supported_candidate" and pc.passages
    assert r.aggregate_status == "supported_candidate"


def test_no_support_found_when_text_exists_but_no_support():
    r = svc().check("severe hepatotoxicity occurred in newborns", ["smith2020"])
    assert r.per_citekey[0].status == "no_support_found"


def test_unverifiable_when_citekey_unresolved():
    r = svc().check("all-cause mortality", ["ghost1999"])
    assert r.per_citekey[0].status == "unverifiable"
    assert r.aggregate_status == "unverifiable"


def test_unverifiable_when_fulltext_unavailable():
    r = svc().check("all-cause mortality", ["nofulltext"])
    assert r.per_citekey[0].status == "unverifiable"


def test_unverifiable_when_require_page_and_no_page():
    # fulltext-only support has char locators but no page -> require_page rejects
    r = svc().check("primary outcome all-cause mortality", ["smith2020"], require_page=True)
    assert r.per_citekey[0].status == "unverifiable"
    assert "page" in (r.per_citekey[0].reason or "")


def test_multiple_citekeys_per_citekey_statuses():
    r = svc().check("primary outcome all-cause mortality", ["smith2020", "jones2019", "ghost"])
    by = {pc.citekey: pc.status for pc in r.per_citekey}
    assert by["smith2020"] == "supported_candidate"
    assert by["jones2019"] == "no_support_found"
    assert by["ghost"] == "unverifiable"


def test_aggregate_status_precedence():
    # supported beats no_support beats unverifiable
    r = svc().check("primary outcome all-cause mortality", ["smith2020", "ghost"])
    assert r.aggregate_status == "supported_candidate"
    r2 = svc().check("cardiovascular mortality was reduced", ["jones2019", "ghost"])
    assert r2.aggregate_status == "no_support_found"
    r3 = svc().check("anything", ["ghost"])
    assert r3.aggregate_status == "unverifiable"


def test_never_returns_plain_supported():
    r = svc().check("primary outcome all-cause mortality", ["smith2020"])
    for pc in r.per_citekey:
        assert pc.status in ("supported_candidate", "no_support_found", "unverifiable")
        assert pc.status != "supported"


def test_does_not_invent_citekeys():
    r = svc().check("all-cause mortality", ["totally_made_up_key"])
    assert r.per_citekey[0].status == "unverifiable"
    assert r.per_citekey[0].passages == []


def test_provenance_present():
    r = svc().check("mortality", ["smith2020"])
    assert r.provenance is not None and r.provenance.tool == "claim_check"
