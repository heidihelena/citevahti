"""CiteVahti localhost side panel (ADR-0007).

The *blind human decision surface*: a narrow browser panel served from loopback
that lets the human record their support rating before any AI opinion is shown.
It owns no integrity logic — every endpoint maps onto existing engine/agent
functions, and the guarded write path reuses the token-gated agent wrappers. The
AI rating is never returned by a read endpoint until a human rating exists.
"""

from __future__ import annotations

from . import manuscript, prefs
from .server import blinded_rating_view, dispatch, make_server, serve

__all__ = ["dispatch", "make_server", "serve", "blinded_rating_view", "manuscript", "prefs"]
