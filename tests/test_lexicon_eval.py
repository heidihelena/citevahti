"""The claim-check lexical layer must not regress against its frozen baseline.

This is the automatic, human-free evaluation of ADR-0009's transparent floor slice:
it runs the real `text.py` over the curated, author-labelled cases in
`validation/claimcheck/lexicon_cases.jsonl` and fails if precision or recall on
either detector falls below the committed baseline, or if an explicitly-negated
contradiction is ever served as support (the hard polarity guard). Known holes
(paraphrase, antonym-without-negation) are reported by the eval, not gated here —
covering them is the AI-model and human layers' job, not the lexicon's.

Offline: imports repo files only, no network, no AI.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_VDIR = _REPO / "validation" / "claimcheck"
_BASELINE = _VDIR / "lexicon_baseline.json"


def _load_eval():
    spec = importlib.util.spec_from_file_location("cv_eval_lexicon", _VDIR / "eval_lexicon.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def scored():
    ev = _load_eval()
    t = ev.load_text_module(str(_REPO))
    cases = ev.load_cases(str(_VDIR / "lexicon_cases.jsonl"))
    return ev, ev.score(cases, t)


def test_no_negated_contradiction_served_as_support(scored):
    _, s = scored
    assert s["negation_leaks"] == 0, (
        f"polarity guard leak — negated contradictions returned as support: "
        f"{s['negation_leak_ids']}"
    )


def test_no_regression_against_frozen_baseline(scored):
    ev, s = scored
    baseline = json.loads(_BASELINE.read_text())
    regs = ev.regressions(ev.baseline_view(s), baseline)
    assert not regs, "lexical-layer regression vs baseline:\n" + "\n".join(regs)


def test_baseline_is_in_sync_with_the_case_set(scored):
    """The committed baseline must describe the current case set — otherwise the
    regression guard silently checks against stale numbers. Re-freeze with
    `python validation/claimcheck/eval_lexicon.py --write-baseline`."""
    ev, s = scored
    baseline = json.loads(_BASELINE.read_text())
    assert baseline["n"] == s["n"], (
        f"baseline covers {baseline['n']} cases but the set now has {s['n']}; "
        f"re-freeze the baseline"
    )
