"""Blinded human -> AI -> adjudication dual-rating engine (step 7).

The AI is an advisory, blinded second rater. It never decides, never sets the
recorded value, and never silently propagates a rating. The human or panel is
always the decider.
"""

from .ai import (
    DEFAULT_LOCAL_MODEL,
    PREFERRED_LOCAL_MODELS,
    AiRater,
    AiRatingOutput,
    FakeAiRater,
    HttpAiRater,
    HttpPoster,
    HttpxPoster,
    build_ai_rater,
    chat_completion,
    list_ollama_models,
    ollama_model_snapshot,
    resolve_ai_connection,
    suggest_local_model,
)
from .engine import RatingEngine

__all__ = [
    "RatingEngine", "AiRater", "AiRatingOutput", "FakeAiRater",
    "HttpAiRater", "HttpPoster", "HttpxPoster", "build_ai_rater",
    "chat_completion", "resolve_ai_connection",
    "list_ollama_models", "suggest_local_model", "ollama_model_snapshot",
    "PREFERRED_LOCAL_MODELS", "DEFAULT_LOCAL_MODEL",
]
