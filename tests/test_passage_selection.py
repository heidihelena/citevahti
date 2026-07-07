"""Full-text passage selection (item 4): multi-sentence windows + section awareness.

Support for a claim often spans two or three sentences and lives in Results, not
the Introduction. Selection now (a) scores sentence WINDOWS so multi-sentence
support surfaces as one passage, (b) keeps the tightest, non-overlapping variant,
and (c) labels each passage's section and prefers Results/Conclusions on a
coverage tie (never overriding coverage). Deterministic; offline.
"""

from __future__ import annotations

from citevahti.retrieval import FullTextDoc, StaticTextSource
from citevahti.retrieval.service import PassageRetrievalService
from citevahti.schemas.common import ItemRef


def _svc(text: str) -> PassageRetrievalService:
    return PassageRetrievalService(StaticTextSource(
        items={"c1": ItemRef(zotero_key="K1", citekey="c1")},
        fulltext={"K1": FullTextDoc(text=text, attachment_key="A1")}))


def _top(text, claim):
    r = _svc(text).retrieve(citekey="c1", query=claim)
    assert r.status == "ok" and r.passages
    return r.passages[0], r.passages


def test_multi_sentence_support_is_selected_as_one_window():
    text = ("Results\n"
            "Drug X reduced mortality. The reduction was statistically significant.\n")
    top, _ = _top(text, "Drug X reduced mortality significantly")
    # the winning passage spans BOTH sentences (neither single one covers the whole claim)
    assert "reduced mortality" in top.quote and "significant" in top.quote
    assert top.score == 1.0            # window covers every claim token; a single sentence did not
    assert top.section == "Results"


def test_section_preferred_on_a_coverage_tie():
    text = ("Introduction\nDrug X reduced mortality.\n\n"
            "Results\nDrug X reduced mortality.\n")
    top, _ = _top(text, "Drug X reduced mortality")
    # both sentences cover the claim equally -> the Results one wins the tie
    assert top.section == "Results"


def test_no_overlapping_passages_returned():
    text = ("Results\n"
            "Drug X reduced mortality. The reduction was statistically significant.\n")
    _, passages = _top(text, "Drug X reduced mortality significantly")
    spans = [(p.char_start, p.char_end) for p in passages]
    for i, (s1, e1) in enumerate(spans):
        for j, (s2, e2) in enumerate(spans):
            if i != j:
                assert not (s2 <= s1 and e1 <= e2)   # no passage fully inside another


def test_no_query_keeps_single_sentence_granularity_and_labels_section():
    text = ("Results\nDrug X reduced mortality. It was significant.\n")
    r = _svc(text).retrieve(citekey="c1")   # no query
    assert len(r.passages) >= 2             # one per sentence, not a merged window
    assert any(p.section == "Results" for p in r.passages)
