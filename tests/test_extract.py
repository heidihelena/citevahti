"""Assistive extraction: candidates with passages, unverifiable, no guessing."""

from citevahti.extract import ExtractService
from citevahti.retrieval import FullTextDoc, StaticTextSource
from citevahti.schemas.common import ItemRef
from citevahti.state import CiteVahtiStore

FIXTURE = (
    "This was a multicenter, randomized, double-blind, placebo-controlled trial. "
    "We enrolled 480 patients with type 2 diabetes. "
    "Participants were randomized to receive metformin or placebo. "
    "The primary outcome was all-cause mortality at 5 years. "
    "The hazard ratio was 0.78 (95% CI 0.65-0.93). "
    "Median follow-up was 5 years."
)


def svc(fulltext=None, items=None):
    return ExtractService(StaticTextSource(items=items or {}, fulltext=fulltext or {}))


def subject():
    return ItemRef(zotero_key="K1", citekey="smith2020")


def doc():
    return {"K1": FullTextDoc(text=FIXTURE, attachment_key="ATT1")}


def test_extracts_sample_size():
    r = svc(doc()).extract(subject(), ["sample_size"])
    assert r.candidates_by_field["sample_size"][0].value == "480"


def test_extracts_design():
    r = svc(doc()).extract(subject(), ["design"])
    assert r.candidates_by_field["design"][0].value == "randomized controlled trial"


def test_extracts_intervention_comparator_outcome():
    r = svc(doc()).extract(subject(), ["intervention", "comparator", "outcome"])
    assert r.candidates_by_field["intervention"][0].value == "metformin"
    assert r.candidates_by_field["comparator"][0].value == "placebo"
    assert r.candidates_by_field["outcome"][0].value == "all-cause mortality"


def test_unverifiable_when_field_absent():
    r = svc({"K1": FullTextDoc(text="A brief unrelated note.")}).extract(subject(), ["sample_size"])
    assert "sample_size" in r.unverifiable_fields
    assert "sample_size" not in r.candidates_by_field


def test_every_candidate_has_a_passage_under_require_passage():
    r = svc(doc()).extract(subject(), None, require_passage=True)
    for cands in r.candidates_by_field.values():
        for c in cands:
            assert c.passage is not None and c.passage.quote.strip()


def test_no_guessing_value_is_only_from_text():
    r = svc(doc()).extract(subject(), ["population"])
    cand = r.candidates_by_field["population"][0]
    assert cand.value.lower() in FIXTURE.lower()  # appears verbatim in the source


def test_extract_does_not_write_evidence_map(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    svc(doc()).extract(subject(), ["design"])  # no store passed; cannot write
    emap = store.load_evidence_map()
    assert emap.nodes == [] and emap.attachments == []
    assert "evidence_map.save" not in [e.event for e in store.audit.entries()]


def test_degraded_when_fulltext_unavailable():
    r = svc({}).extract(subject(), ["design"])
    assert r.status == "degraded" and r.error_code == "full_text_unavailable"
    assert r.unverifiable_fields == ["design"]


def test_exact_citekey_resolution_only():
    # citekey-only subject that does not resolve -> degraded, never invented
    s = svc(doc())
    r = s.extract(ItemRef(zotero_key="", citekey="ghost"), ["design"])
    assert r.status == "degraded" and r.error_code == "citekey_unresolved"
    # one that resolves through the source
    s2 = ExtractService(StaticTextSource(items={"smith2020": subject()}, fulltext=doc()))
    r2 = s2.extract(ItemRef(zotero_key="", citekey="smith2020"), ["design"])
    assert r2.status == "ok" and "design" in r2.candidates_by_field


def test_provenance_present():
    r = svc(doc()).extract(subject(), ["design"])
    assert r.provenance is not None and r.provenance.tool == "extract"
