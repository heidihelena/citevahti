"""Population / PICO fit — the deterministic floor flag (ADR-0009 "floor flags,
AI confirms"). A source can support the claimed relation yet be about a different
population; population_mismatch() raises an inspectable, advisory warning when
BOTH sides name a different population on the same axis. It must NOT fire when a
population is implicit, or when the two sides name the same pole — over-firing
would be worse than silence (the AI layer covers the implicit cases).

Offline: imports repo files only.
"""

from __future__ import annotations

from citevahti.claimcheck import ClaimCheckService
from citevahti.retrieval import FullTextDoc, StaticTextSource
from citevahti.retrieval.text import population_mismatch
from citevahti.schemas.common import ItemRef


# ---- text.py unit ----------------------------------------------------------
def test_population_mismatch_fires_on_different_population():
    assert population_mismatch("reduces seizures in children", "reduced seizures in adults")
    assert population_mismatch("improves survival in humans", "improved survival in mice")
    assert population_mismatch("lowers cholesterol in men", "lowered cholesterol in women")


def test_population_cue_is_inspectable():
    assert population_mismatch("effect in children", "effect in adults") == "children ≠ adults"


def test_population_mismatch_silent_when_implicit_or_same():
    # same population -> no flag
    assert population_mismatch("reduces seizures in children", "reduced seizures in children") is None
    # population implicit on one side -> no flag (that is the AI layer's job)
    assert population_mismatch("lowers cholesterol in adults", "lowered cholesterol") is None
    # "patients" is not a population-axis cue -> no flag
    assert population_mismatch("improves survival in humans", "improved survival in the patients") is None
    # same pole via a synonym (women/female) -> no flag
    assert population_mismatch("helps women", "helped female participants") is None


def test_cross_axis_populations_do_not_falsely_conflict():
    # a sex cue vs an age cue are different axes, not a mismatch
    assert population_mismatch("effect in men", "effect in children") is None


# ---- service: advisory warning, NOT a status change ------------------------
def _svc():
    return ClaimCheckService(StaticTextSource(
        items={"peds2021": ItemRef(zotero_key="K1", citekey="peds2021")},
        fulltext={"K1": FullTextDoc(
            text="The drug reduced seizures in adults over a 6-month period.",
            attachment_key="A1")},
    ))


def test_population_mismatch_is_a_warning_not_a_downgrade():
    r = _svc().check("The drug reduces seizures in children", ["peds2021"])
    pc = r.per_citekey[0]
    assert pc.status == "supported_candidate"          # still support — NOT downgraded
    assert pc.population_cue == "children ≠ adults"     # but the mismatch is surfaced
    assert any("different population" in w for w in r.warnings)
