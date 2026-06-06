"""The AiRater seam.

The rater is BLIND: it never receives the human value. Unit tests use
``FakeAiRater``; no real model is called in step 7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from ..schemas.common import PassageRef


@dataclass
class AiRatingOutput:
    value: Optional[str] = None
    abstained: bool = False
    confidence: Optional[float] = None
    supporting_passages: list[PassageRef] = field(default_factory=list)
    domain_reasoning: Optional[str] = None


@runtime_checkable
class AiRater(Protocol):
    # NOTE: the signature intentionally excludes any human value.
    def rate(self, *, frame, scheme, subject, task_type: str) -> AiRatingOutput: ...


class FakeAiRater:
    """Deterministic offline rater for tests."""

    def __init__(self, value: Optional[str] = None, abstained: bool = False,
                 confidence: Optional[float] = None,
                 supporting_passages: Optional[list[PassageRef]] = None,
                 domain_reasoning: Optional[str] = None) -> None:
        self._out = AiRatingOutput(value=None if abstained else value, abstained=abstained,
                                   confidence=confidence,
                                   supporting_passages=supporting_passages or [],
                                   domain_reasoning=domain_reasoning)

    def rate(self, *, frame, scheme, subject, task_type: str) -> AiRatingOutput:
        return self._out
