"""Curated biomedical synonym normalization for lexical matching.

The lexical layer was synonymy-blind ("heart attack" ≠ "myocardial infarction"),
so a genuinely-supporting source was returned as no-support and a student might
drop a good citation. A small, high-precision map folds unambiguous equivalents to
a canonical token in the MATCHING path only. It must (a) make the equivalents
match, (b) leave the display tokens raw, and (c) not fire on unrelated text.
Precision on the full case set is guarded by test_lexicon_eval.py.

Offline: imports repo files only.
"""

from __future__ import annotations

from citevahti.retrieval.text import content_tokens, coverage_score, normalize_synonyms


def test_known_equivalents_fold_together():
    assert normalize_synonyms("heart attack") == normalize_synonyms("myocardial infarction")
    assert normalize_synonyms("high blood pressure") == normalize_synonyms("hypertension")
    assert normalize_synonyms("type 2 diabetes") == normalize_synonyms("T2DM")


def test_coverage_now_matches_across_a_synonym():
    cov = coverage_score(
        "Aspirin lowers the risk of heart attack",
        "Aspirin reduced the incidence of myocardial infarction",
    )
    assert cov >= 0.5


def test_unrelated_text_is_untouched():
    # a phrase that isn't a known equivalent passes through unchanged
    assert normalize_synonyms("the study examined dosing") == "the study examined dosing"


def test_display_tokens_stay_raw():
    # matching normalizes, but the human-facing token set is the original words
    assert "attack" in content_tokens("risk of heart attack")
    assert "myocardialinfarction" not in content_tokens("risk of heart attack")
