"""'overstated' verdict: the cited paper supports a weaker claim than the one made.

The most common real citation-integrity failure is not a fabricated reference or a
flat contradiction — it is overclaim. This pins 'overstated' into the support
vocabulary, maps it to the existing 'overclaim' finding, and asserts it can NEVER
back an 'accept' decision.
"""

from citevahti import findings
from citevahti.schemas.claim_support import SUPPORT_VALUES
from citevahti.schemas.decision import SUPPORTING_VALUES


def test_overstated_is_a_support_value():
    assert "overstated" in SUPPORT_VALUES


def test_overstated_maps_to_the_overclaim_finding():
    assert findings.support_to_finding("overstated") == "overclaim"
    assert findings.is_finding("overclaim")


def test_overstated_cannot_back_an_accept():
    # The decision validator only accepts SUPPORTING_VALUES as supporting the claim;
    # 'overstated' is a failure mode and must stay out of that set.
    assert "overstated" not in SUPPORTING_VALUES


def test_every_support_value_still_maps_to_a_finding():
    for v in SUPPORT_VALUES:
        f = findings.support_to_finding(v)
        assert f is not None and findings.is_finding(f)
