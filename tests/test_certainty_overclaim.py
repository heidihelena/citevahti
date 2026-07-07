"""Certainty / overclaim flag (item 5) — the claim asserts a relation plainly while
the source only supports it weakly or correlationally ("associated with", "modest",
"nonsignificant"). certainty_mismatch() raises an inspectable, ADVISORY warning; it
is NOT a status change and never fires when the claim is itself hedged. A
high-precision cue set by design (no bare "may/could" on the passage side).

Offline: imports repo files only.
"""

from __future__ import annotations

from citevahti.claimcheck import ClaimCheckService
from citevahti.retrieval import FullTextDoc, StaticTextSource
from citevahti.retrieval.text import certainty_mismatch
from citevahti.schemas.common import ItemRef


# ---- text.py unit ----------------------------------------------------------
def test_overclaim_fires_when_source_is_correlational_or_weak():
    assert certainty_mismatch("Coffee reduces heart disease",
                              "Coffee was associated with lower heart disease rates")
    assert certainty_mismatch("The drug prevents relapse",
                              "The drug showed a modest reduction in relapse")
    assert certainty_mismatch("Exercise improves memory",
                              "Exercise was correlated with better memory")


def test_no_overclaim_when_claim_is_itself_hedged():
    # claim already tentative -> not an overclaim
    assert certainty_mismatch("The drug may prevent relapse",
                              "The drug was associated with fewer relapses") is None


def test_no_overclaim_when_source_states_it_plainly():
    assert certainty_mismatch("Coffee reduces heart disease",
                              "Coffee reduced heart disease incidence significantly") is None


def test_bare_modals_in_passage_do_not_trigger():
    # "may" is deliberately NOT a passage trigger (it attaches to sub-clauses)
    assert certainty_mismatch("The drug reduces mortality",
                              "The drug reduced mortality and may improve quality of life") is None


# ---- service: advisory warning, not a status change ------------------------
def _svc(text):
    return ClaimCheckService(StaticTextSource(
        items={"c1": ItemRef(zotero_key="K1", citekey="c1")},
        fulltext={"K1": FullTextDoc(text=text, attachment_key="A1")}))


def test_overclaim_is_a_warning_not_a_downgrade():
    r = _svc("Coffee was associated with lower heart disease rates.").check(
        "Coffee reduces heart disease", ["c1"])
    pc = r.per_citekey[0]
    assert pc.status == "supported_candidate"       # still support — NOT downgraded
    assert pc.certainty_cue == "associated"         # but the overclaim risk is surfaced
    assert any("overclaim" in w for w in r.warnings)
