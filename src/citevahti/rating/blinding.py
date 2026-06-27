"""The one blinding rule, in one place.

Blinding is CiteVahti's core safety property: the AI's support rating must stay hidden
until the human has committed their own, so the human is never anchored. A *blinding leak*
(the AI value visible before the human rates) is a security issue (see ``SECURITY.md``).

The reveal decision is **deterministic** — a pure function of ledger state (does a human
rating exist?), with no dependence on timing, ordering, or randomness. The AI may have been
recorded long before; it stays sealed until — and only until — a human rating exists.

Every surface that shows a support rating (the loopback panel, the agent's ``get_provenance``,
and the report) MUST derive blinding through these functions rather than re-implementing the
rule, so the surfaces are provably consistent and cannot drift apart. Each surface keeps its
own display string for the hidden state via the ``hidden`` argument.
"""

from __future__ import annotations

from typing import Optional


def reveal_ai(human_value: Optional[str]) -> bool:
    """True iff the AI rating may be revealed — i.e. a human rating exists.

    This single predicate is the whole blinding rule. It is intentionally a function of
    *state* (a human value is present) and nothing else: not the order ratings were recorded
    in, not a timestamp, not a flag that could be set early.
    """
    return human_value is not None


def blinded_ai_value(human_value: Optional[str], ai_value: Optional[str],
                     *, hidden: str = "hidden") -> Optional[str]:
    """Apply the blinding rule to one pair of (human, AI) values.

    Returns the AI value once the human has rated; the ``hidden`` sentinel while they
    haven't (callers pass their own display string, e.g. ``"hidden (blinded until human
    rates)"``); and ``None`` when there is no AI rating at all (nothing to blind).
    """
    if ai_value is None:
        return None
    return ai_value if reveal_ai(human_value) else hidden
