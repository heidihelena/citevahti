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


# --- Polarity / direction (deterministic; no AI, no embeddings) --------------
# Lexical coverage is DIRECTION-BLIND: "X reduced mortality" and "X did NOT
# reduce mortality" share their content tokens, so a contradicting passage scores
# as high as a supporting one. These cues let claim-check tell a SUPPORT candidate
# apart from a CONTRADICTION candidate, so a negated passage is never silently
# returned as support. This is a correctness floor, not semantic understanding:
# paraphrase / synonymy still need the advisory layer downstream.
#
# Ordered tuples (not sets) so negation_cue() returns a stable, inspectable cue.
_NEGATION_PHRASES = (
    "no longer", "did not", "does not", "do not", "was not", "were not",
    "is not", "are not", "not associated", "no association", "no significant",
    "no difference", "no effect", "no evidence",
)
_NEGATION_CUES = (
    "no", "not", "never", "without", "neither", "nor", "none", "non",
    "cannot", "fail", "fails", "failed", "lack", "lacks", "lacked",
    "absence", "absent", "unable", "unchanged", "unaffected",
)


def negation_cue(text: str) -> str | None:
    """The first negation cue in ``text`` (multi-word phrase preferred), else None.

    Returned so a contradiction candidate is *inspectable* — the human sees which
    word flipped the polarity ("did not"), not just a verdict.
    """
    low = text.lower()
    for phrase in _NEGATION_PHRASES:
        if phrase in low:
            return phrase
    toks = set(tokenize(low))
    for cue in _NEGATION_CUES:
        if cue in toks:
            return cue
    return None


def has_negation(text: str) -> bool:
    """True if ``text`` carries a sentential negation of its main relation."""
    return negation_cue(text) is not None


def polarity_conflict(query: str, passage: str) -> bool:
    """True when query and passage assert OPPOSITE polarity on a shared relation.

    Conservative: only fires when they actually overlap lexically (same relation
    being discussed) AND differ in negation parity. Same-parity (both asserted, or
    both negated) is NOT a conflict — a negated claim is supported by a negated
    passage.
    """
    if coverage_score(query, passage) <= 0.0:
        return False
    return has_negation(query) != has_negation(passage)


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
