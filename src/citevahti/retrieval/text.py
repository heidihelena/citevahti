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
    """Tokens used for lexical matching: drop stopwords + 1-char tokens.

    Returns the RAW (unstemmed) content words — this is what the panel shows as
    "present / missing", so it must stay human-readable. Matching itself stems
    (see ``coverage_score``)."""
    return {t for t in tokenize(text) if t not in _STOPWORDS}


# --- Conservative inflectional stemmer (deterministic; no AI) -----------------
# Coverage was direction-blind AND inflection-blind: "antidepressants" did not
# match "antidepressant", "increases" did not match "increased". This shallow
# stemmer folds common English inflections so different forms of the SAME word
# match, recovering recall the eval flagged. It is deliberately INFLECTIONAL, not
# a full derivational stemmer — kept shallow because it sits in the audited
# coverage path, and every change is measured for precision by the lexicon eval.
# It is applied only for MATCHING (coverage_score); content_tokens stays raw.
_STEM_SUFFIXES = (
    ("ies", "y"), ("ied", "y"), ("ing", ""), ("edly", ""), ("edness", ""),
    ("ed", ""), ("est", ""), ("ers", ""), ("er", ""), ("es", ""),
    ("ally", "al"), ("ly", ""), ("al", ""), ("s", ""), ("e", ""),
)
_MIN_STEM = 4  # never strip below this many characters — guards short words


def stem(token: str) -> str:
    """Fold a token to a shallow inflectional stem (iterated to a fixed point).

    Conservative by design: the ``_MIN_STEM`` floor stops it from mangling short
    words, so e.g. "less"/"loss"/"rate" are left intact while "reduced",
    "reduces", "reducing" and "reduce" all fold to "reduc"."""
    tok = token
    changed = True
    while changed and len(tok) > _MIN_STEM:
        changed = False
        for suf, repl in _STEM_SUFFIXES:
            if suf and tok.endswith(suf) and len(tok) - len(suf) + len(repl) >= _MIN_STEM:
                tok = tok[: -len(suf)] + repl
                changed = True
                break
    return tok


def content_stems(text: str) -> set[str]:
    """Stemmed content tokens — the set used for lexical MATCHING."""
    return {stem(t) for t in content_tokens(text)}


def coverage_score(query: str, passage: str) -> float:
    """Fraction of the query's content stems present in the passage (0..1)."""
    q = content_stems(query)
    if not q:
        return 0.0
    p = content_stems(passage)
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


# --- Direction / antonym polarity (deterministic; no AI) ---------------------
# Negation is not the only way a passage opposes a claim: an OPPOSITE DIRECTION
# on a shared relation does too — "X reduced mortality" vs "X increased
# mortality" share their nouns but assert opposite directions, and carry NO
# negation cue for negation_cue() to catch. These paired families let
# polarity_conflict() see that opposition. Two INDEPENDENT axes so cross-axis
# terms (e.g. "increased" vs "worsened") do not falsely conflict; a text that
# mentions both poles of an axis is ambiguous on that axis and ignored. Still a
# lexical, inspectable cue list — not semantics; paraphrase/synonymy stays the
# advisory layer's job.
_DIRECTION_AXES: dict[str, dict[str, frozenset[str]]] = {
    "magnitude": {
        "up": frozenset({
            "increase", "increased", "increases", "increasing", "rise", "rises",
            "rising", "rose", "risen", "higher", "greater", "more", "elevated",
            "elevate", "elevates", "raise", "raised", "raises", "grew", "grow",
            "grows", "growing", "gain", "gained", "gains", "upregulated",
            "upregulation",
        }),
        "down": frozenset({
            "decrease", "decreased", "decreases", "decreasing", "reduce",
            "reduced", "reduces", "reducing", "lower", "lowered", "lowers",
            "lowering", "fall", "falls", "falling", "fell", "fallen", "fewer",
            "less", "lessen", "lessened", "lessens", "decline", "declined",
            "declines", "drop", "dropped", "drops", "loss", "lost", "shorten",
            "shortened", "shortens", "shorter", "downregulated", "downregulation",
        }),
    },
    "quality": {
        "better": frozenset({
            "improve", "improved", "improves", "improving", "better", "benefit",
            "benefited", "benefits", "beneficial", "ameliorate", "ameliorated",
            "ameliorates",
        }),
        "worse": frozenset({
            "worsen", "worsened", "worsens", "worsening", "worse", "harm",
            "harmed", "harms", "harmful", "deteriorate", "deteriorated",
            "deteriorates", "aggravate", "aggravated", "aggravates",
        }),
    },
}


def _matched_direction(text: str) -> dict[str, tuple[str, str]]:
    """{axis: (pole, first_matched_word)} for axes with EXACTLY one pole present."""
    toks = set(tokenize(text))
    out: dict[str, tuple[str, str]] = {}
    for axis, poles in _DIRECTION_AXES.items():
        present = {pole: (toks & words) for pole, words in poles.items()}
        present = {pole: hit for pole, hit in present.items() if hit}
        if len(present) == 1:
            pole, hit = next(iter(present.items()))
            out[axis] = (pole, sorted(hit)[0])
    return out


def direction_opposes(query: str, passage: str) -> bool:
    """True if query and passage assert OPPOSITE poles on a shared direction axis."""
    q, p = _matched_direction(query), _matched_direction(passage)
    return any(axis in p and p[axis][0] != pole for axis, (pole, _w) in q.items())


def direction_cue(query: str, passage: str) -> str | None:
    """Name the opposing direction words (e.g. ``reduced ≠ increased``), else None."""
    q, p = _matched_direction(query), _matched_direction(passage)
    for axis, (pole, qword) in q.items():
        if axis in p and p[axis][0] != pole:
            return f"{qword} ≠ {p[axis][1]}"
    return None


def polarity_conflict(query: str, passage: str) -> bool:
    """True when query and passage assert OPPOSITE polarity on a shared relation.

    Conservative: only fires when they actually overlap lexically (same relation
    being discussed). Polarity is flipped by two independent mechanisms — sentential
    **negation** and **opposite direction** (antonym) — combined by XOR, so a single
    flip is a conflict but a *double* flip cancels ("X reduced mortality" vs "X did
    not increase mortality" is NOT a conflict). Same-parity (both asserted, both
    negated, or same direction) is not a conflict.
    """
    if coverage_score(query, passage) <= 0.0:
        return False
    negation_differs = has_negation(query) != has_negation(passage)
    return negation_differs != direction_opposes(query, passage)  # XOR


def polarity_cue(query: str, passage: str) -> str | None:
    """The cue that flips polarity between query and passage — the negation word, or
    the opposing direction pair — for an *inspectable* contradiction. None if no
    conflict."""
    if not polarity_conflict(query, passage):
        return None
    if has_negation(query) != has_negation(passage):
        return negation_cue(passage) or negation_cue(query)
    return direction_cue(query, passage)


# --- Population / PICO fit (deterministic; no AI) ----------------------------
# A source can support the claimed RELATION yet be about a different POPULATION —
# "works in adults" cited for a paediatric claim, a mouse study cited for a human
# claim. Lexically that looks like clean support (same nouns, same direction), so
# neither coverage nor polarity catches it. These axes let population_mismatch()
# raise an inspectable "population may differ" WARNING — never a verdict, and it
# does NOT change the support/contradiction status; the human/AI layer adjudicates
# (ADR-0009 "floor flags, AI confirms"). Conservative by design: it fires only when
# BOTH sides name a population on the SAME axis and the poles differ. It is silent
# when a side leaves its population implicit (the common case), which is exactly
# what the AI layer is there to cover.
_POPULATION_AXES: dict[str, dict[str, frozenset[str]]] = {
    "age": {
        "pediatric": frozenset({
            "child", "children", "childhood", "pediatric", "paediatric",
            "infant", "infants", "infancy", "neonatal", "neonate", "neonates",
            "adolescent", "adolescents", "juvenile", "juveniles",
        }),
        "adult": frozenset({"adult", "adults", "adulthood"}),
        "elderly": frozenset({"elderly", "geriatric", "octogenarian", "octogenarians"}),
    },
    "sex": {
        "male": frozenset({"men", "male", "males", "boys"}),
        "female": frozenset({"women", "female", "females", "girls"}),
    },
    "species": {
        "nonhuman": frozenset({
            "mouse", "mice", "murine", "rat", "rats", "rodent", "rodents",
            "canine", "porcine", "bovine", "primate", "primates", "zebrafish",
            "drosophila", "animal", "animals",
        }),
        "human": frozenset({"human", "humans"}),
    },
}


def _matched_population(text: str) -> dict[str, tuple[str, str]]:
    """{axis: (pole, first_matched_word)} for population axes with EXACTLY one pole."""
    toks = set(tokenize(text))
    out: dict[str, tuple[str, str]] = {}
    for axis, poles in _POPULATION_AXES.items():
        present = {pole: (toks & words) for pole, words in poles.items()}
        present = {pole: hit for pole, hit in present.items() if hit}
        if len(present) == 1:
            pole, hit = next(iter(present.items()))
            out[axis] = (pole, sorted(hit)[0])
    return out


def population_mismatch(query: str, passage: str) -> str | None:
    """Inspectable cue (e.g. ``children ≠ adults``) if query and passage name a
    DIFFERENT population on a shared axis, else None. Advisory only — a review
    prompt on an otherwise-supporting citation, never a verdict."""
    q, p = _matched_population(query), _matched_population(passage)
    for axis, (pole, qword) in q.items():
        if axis in p and p[axis][0] != pole:
            return f"{qword} ≠ {p[axis][1]}"
    return None


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
