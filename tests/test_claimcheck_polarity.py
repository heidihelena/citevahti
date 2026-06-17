"""Polarity / direction guard for claim-check (correctness floor).

Lexical coverage is direction-blind, so a contradicting passage used to score as
support. These tests lock the fix: a negated passage over the same relation is a
``contradiction_candidate``, never ``supported_candidate``. Paraphrase / synonymy
are intentionally NOT handled here (that is the advisory layer's job).

They also lock the two improvements over the original patch:
  * the contradiction is *inspectable* — ``polarity_cue`` names the negation word;
  * a source with BOTH a supporting and an opposing passage surfaces the conflict
    (passages + cue + warning) instead of silently dropping the opposing one.
"""

from __future__ import annotations

from citevahti.claimcheck import ClaimCheckService
from citevahti.retrieval import FullTextDoc, StaticTextSource
from citevahti.retrieval.text import has_negation, negation_cue, polarity_conflict
from citevahti.schemas.common import ItemRef


# ---- text.py units (no source) ---------------------------------------------
def test_has_negation_detects_sentential_negation():
    assert has_negation("Drug X did not reduce mortality")
    assert has_negation("no association between X and Y")
    assert has_negation("there was no significant effect")
    assert not has_negation("Drug X reduced mortality significantly")
    assert not has_negation("X was associated with higher risk")


def test_negation_cue_is_inspectable():
    assert negation_cue("Drug X did not reduce mortality") == "did not"
    assert negation_cue("no association was seen") == "no association"
    assert negation_cue("the drug failed to lower risk") == "failed"
    assert negation_cue("Drug X reduced mortality") is None


def test_polarity_conflict_needs_overlap_and_opposite_parity():
    assert polarity_conflict("Drug X reduced mortality", "Drug X did not reduce mortality")
    # same parity (both negated) is NOT a conflict
    assert not polarity_conflict("Drug X did not reduce mortality",
                                 "Drug X did not reduce mortality")
    # both asserted -> no conflict
    assert not polarity_conflict("Drug X reduced mortality", "Drug X reduced mortality")
    # no lexical overlap -> conservative, no conflict
    assert not polarity_conflict("Drug X reduced mortality", "unrelated agriculture text")


# ---- service: candidate-only statuses with the direction guard --------------
def _src():
    return StaticTextSource(
        items={
            "pos2020": ItemRef(zotero_key="K1", citekey="pos2020"),
            "neg2020": ItemRef(zotero_key="K2", citekey="neg2020"),
            "mix2020": ItemRef(zotero_key="K3", citekey="mix2020"),
        },
        fulltext={
            "K1": FullTextDoc(text="Drug X reduced mortality significantly in the trial.",
                              attachment_key="A1"),
            "K2": FullTextDoc(text="Drug X did not reduce mortality in the trial.",
                              attachment_key="A2"),
            "K3": FullTextDoc(
                text="Drug X reduced mortality significantly overall. "
                     "Drug X did not reduce mortality in the elderly subgroup.",
                attachment_key="A3"),
        },
    )


def _svc():
    return ClaimCheckService(_src())


CLAIM = "Drug X reduced mortality"


def test_supporting_passage_is_supported():
    pc = _svc().check(CLAIM, ["pos2020"]).per_citekey[0]
    assert pc.status == "supported_candidate"
    assert pc.polarity_cue is None


def test_negated_passage_is_contradiction_not_support():
    r = _svc().check(CLAIM, ["neg2020"])
    pc = r.per_citekey[0]
    assert pc.status == "contradiction_candidate"          # never silently "supported"
    assert pc.polarity_cue == "did not"                    # inspectable: which word flipped it
    assert pc.passages                                     # the opposing passage is shown
    assert r.aggregate_status == "contradiction_candidate"


def test_negated_claim_supported_by_negated_passage():
    # same-parity: a negated claim IS supported by a negated passage (no false conflict)
    pc = _svc().check("Drug X did not reduce mortality", ["neg2020"]).per_citekey[0]
    assert pc.status == "supported_candidate"


def test_mixed_source_surfaces_the_conflict_not_hidden():
    r = _svc().check(CLAIM, ["mix2020"])
    pc = r.per_citekey[0]
    assert pc.status == "supported_candidate"              # real support exists
    assert pc.polarity_cue == "did not"                    # but the opposing passage is flagged
    assert len(pc.passages) >= 2                           # BOTH passages kept, not dropped
    assert any("opposing passage" in w for w in r.warnings)


def test_contradiction_leads_the_headline_across_sources():
    r = _svc().check(CLAIM, ["pos2020", "neg2020"])
    assert r.aggregate_status == "contradiction_candidate"  # the contradiction is surfaced
    assert any("conflicting evidence" in w for w in r.warnings)
