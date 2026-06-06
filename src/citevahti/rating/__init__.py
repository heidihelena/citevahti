"""Blinded human -> AI -> adjudication dual-rating engine (step 7).

The AI is an advisory, blinded second rater. It never decides, never sets the
recorded value, and never silently propagates a rating. The human or panel is
always the decider.
"""

from .ai import AiRater, AiRatingOutput, FakeAiRater
from .engine import RatingEngine

__all__ = ["RatingEngine", "AiRater", "AiRatingOutput", "FakeAiRater"]
