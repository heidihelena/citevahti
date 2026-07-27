"""Blinded human -> AI -> adjudication dual-rating engine (step 7).

The AI is an advisory, blinded second rater. It never decides, never sets the
recorded value, and never silently propagates a rating. The human or panel is
always the decider.
"""

from .ai import (
    AI_RETRY_ATTEMPTS,
    AI_RETRY_BACKOFF_S,
    API_MAX_REPLY_TOKENS,
    DEFAULT_LOCAL_MODEL,
    LOCAL_MAX_REPLY_TOKENS,
    PREFERRED_LOCAL_MODELS,
    RETRYABLE_FAILURE_KINDS,
    TRUNCATED_REPLY_REASON,
    AiRater,
    AiRatingOutput,
    ChatReply,
    FakeAiRater,
    HttpAiRater,
    HttpPoster,
    HttpxPoster,
    build_ai_rater,
    chat_completion,
    chat_reply,
    is_truncation_reason,
    list_ollama_models,
    ollama_model_snapshot,
    rate_with_retry,
    resolve_ai_connection,
    suggest_local_model,
)
from .engine import RatingEngine

__all__ = [
    "RatingEngine", "AiRater", "AiRatingOutput", "FakeAiRater",
    "HttpAiRater", "HttpPoster", "HttpxPoster", "build_ai_rater",
    "chat_completion", "chat_reply", "ChatReply", "resolve_ai_connection",
    "TRUNCATED_REPLY_REASON", "is_truncation_reason",
    "LOCAL_MAX_REPLY_TOKENS", "API_MAX_REPLY_TOKENS",
    "list_ollama_models", "suggest_local_model", "ollama_model_snapshot",
    "PREFERRED_LOCAL_MODELS", "DEFAULT_LOCAL_MODEL",
    "rate_with_retry", "AI_RETRY_ATTEMPTS", "AI_RETRY_BACKOFF_S",
    "RETRYABLE_FAILURE_KINDS",
]
