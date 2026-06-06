"""Deterministic text segmentation + lexical scoring (no AI, no embeddings)."""

from __future__ import annotations

import re

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "was",
    "were", "is", "are", "be", "by", "at", "as", "that", "this", "from", "it",
    "we", "our", "study", "patients", "group", "groups", "than", "had", "has",
}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1]


def content_tokens(text: str) -> set[str]:
    """Tokens used for lexical matching: drop stopwords + 1-char tokens."""
    return {t for t in tokenize(text) if t not in _STOPWORDS}


def coverage_score(query: str, passage: str) -> float:
    """Fraction of the query's content tokens present in the passage (0..1)."""
    q = content_tokens(query)
    if not q:
        return 0.0
    p = content_tokens(passage)
    return len(q & p) / len(q)


_SENT_END = re.compile(r"[.!?]+(?=\s|$)|\n+")


def segment_sentences(text: str) -> list[tuple[int, int, str]]:
    """Split ``text`` into (char_start, char_end, quote) over non-empty spans.

    Offsets index into the original text (for audit); ``quote`` is the stripped
    span. Deterministic; no language model.
    """
    out: list[tuple[int, int, str]] = []
    start = 0
    for m in _SENT_END.finditer(text):
        end = m.end()
        span = text[start:end]
        if span.strip():
            out.append((start, end, span.strip()))
        start = end
    if start < len(text):
        span = text[start:]
        if span.strip():
            out.append((start, len(text), span.strip()))
    return out


def sentence_containing(text: str, pos: int) -> tuple[int, int, str]:
    """Return the (start, end, quote) of the sentence containing offset ``pos``."""
    for start, end, quote in segment_sentences(text):
        if start <= pos < end:
            return start, end, quote
    # fallback: whole text
    return 0, len(text), text.strip()
