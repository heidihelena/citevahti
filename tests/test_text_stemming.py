"""The conservative inflectional stemmer that backs lexical coverage matching.

It must (a) fold common inflections of the SAME word together so coverage isn't
inflection-blind, and (b) NOT mangle short words below the length floor, which is
what keeps it from inventing false matches in the audited coverage path. Precision
on the full case set is guarded separately by test_lexicon_eval.py.

Offline: imports repo files only.
"""

from __future__ import annotations

from citevahti.retrieval.text import content_tokens, coverage_score, stem


def test_inflections_of_the_same_word_fold_together():
    assert stem("antidepressants") == stem("antidepressant")
    for form in ("reduced", "reduces", "reducing", "reduce"):
        assert stem(form) == stem("reduce")
    assert stem("increases") == stem("increased")
    assert stem("higher") == stem("high")
    assert stem("suicidal") == stem("suicide")


def test_short_words_are_not_mangled():
    # the _MIN_STEM floor protects these — over-stemming here would create
    # surprising matches in the coverage path
    for w in ("less", "loss", "rate", "risk", "dose", "gene"):
        assert len(stem(w)) >= 4


def test_coverage_now_matches_inflected_forms():
    # the case the eval flagged: plural/inflected forms used to score below threshold
    cov = coverage_score(
        "Antidepressants increase suicide risk in adolescents",
        "Antidepressant use was associated with increased suicidal ideation in adolescents",
    )
    assert cov >= 0.5


def test_content_tokens_stay_raw_for_display():
    # matching stems, but the human-facing token set is unstemmed
    assert "antidepressants" in content_tokens("Antidepressants increase risk")
