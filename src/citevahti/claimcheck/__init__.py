"""Deterministic claim checking (step 4).

Lexical support detection only. Never asserts a claim is true; the only positive
status is ``supported_candidate``. Never invents citekeys; exact resolution only.
"""

from .service import ClaimCheckService

__all__ = ["ClaimCheckService"]
