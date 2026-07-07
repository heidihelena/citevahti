"""The published evaluation page must stay in sync with the frozen eval baseline.

`docs/EVALUATION.md` is generated from `validation/claimcheck/lexicon_baseline.json`
by `validation/eval_report.py`. This golden-file test regenerates it and asserts the
committed page matches — so the published numbers can never silently drift from the
measured ones. If it fails: `python validation/eval_report.py --write`.

Offline: imports repo files only.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_GEN = _REPO / "validation" / "eval_report.py"
_DOC = _REPO / "docs" / "EVALUATION.md"
_BASELINE = _REPO / "validation" / "claimcheck" / "lexicon_baseline.json"


def _load():
    spec = importlib.util.spec_from_file_location("cv_eval_report", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_published_page_matches_the_frozen_baseline():
    mod = _load()
    baseline = json.loads(_BASELINE.read_text())
    assert _DOC.read_text() == mod.build(baseline), (
        "docs/EVALUATION.md is out of sync with the eval baseline — "
        "re-run `python validation/eval_report.py --write`"
    )


def test_page_reports_the_actual_baseline_numbers():
    baseline = json.loads(_BASELINE.read_text())
    doc = _DOC.read_text()
    # the support/contradiction precision from the baseline must appear verbatim
    assert f"{baseline['support_precision']:.3f}" in doc
    assert f"{baseline['contradiction_precision']:.3f}" in doc
    # and the honest gap must be stated
    assert "No whole-system accuracy benchmark" in doc
