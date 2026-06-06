"""Assistive, deterministic field extraction (step 4).

Regex/rule-based candidate extraction with supporting passages. Never guesses,
never writes to the evidence map, no AI behavior, no assessment/GRADE/RoB.
"""

from .service import ExtractService

__all__ = ["ExtractService"]
