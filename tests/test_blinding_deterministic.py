"""The blinding rule is one deterministic, pure function of state.

Blinding is the core safety property (a leak = a security issue, per SECURITY.md). These
lock the canonical rule in ``rating/blinding.py``: the reveal decision depends only on
whether a human rating exists — not on timing, ordering, or how many times it's evaluated.
The cross-surface consistency (panel == provenance == report) lives in
``test_panel_api.py::test_blinding_is_consistent_across_surfaces``, also in this group.
"""

import pytest

from citevahti.rating.blinding import blinded_ai_value, reveal_ai

pytestmark = pytest.mark.security   # blinding leak = a listed security issue


def test_reveal_is_purely_state_based():
    # the whole rule: reveal iff a human value exists. Nothing else can flip it.
    assert reveal_ai("directly_supports") is True
    assert reveal_ai("contradicts") is True
    assert reveal_ai(None) is False


def test_blinded_value_hides_until_human_then_reveals():
    # no human yet -> the AI value is replaced by the hidden sentinel (never leaked)
    assert blinded_ai_value(None, "does_not_support") == "hidden"
    # human has rated -> the AI value is revealed verbatim
    assert blinded_ai_value("directly_supports", "does_not_support") == "does_not_support"


def test_no_ai_rating_is_none_not_hidden():
    # nothing to blind when there's no AI rating at all
    assert blinded_ai_value(None, None) is None
    assert blinded_ai_value("directly_supports", None) is None


def test_caller_supplies_its_own_hidden_string():
    # each surface keeps its display wording; the rule is the same
    assert blinded_ai_value(None, "x", hidden="hidden (blinded until human rates)") \
        == "hidden (blinded until human rates)"


def test_is_deterministic_and_idempotent():
    # same inputs -> same output, every time; evaluation order/repetition cannot change it
    # (this is what makes the blinding "deterministic" — no hidden state, no timestamps)
    for _ in range(5):
        assert blinded_ai_value(None, "contradicts") == "hidden"
        assert blinded_ai_value("contradicts", "contradicts") == "contradicts"
    # the AI value itself never affects the reveal *decision* — only the human's presence does
    for ai in ("directly_supports", "does_not_support", "contradicts", ""):
        assert blinded_ai_value(None, ai) == "hidden"        # always hidden pre-human
        assert blinded_ai_value("any_human", ai) == ai       # always shown post-human
