"""The frozen support vocabulary has exactly one source — and every copy must match it.

``SUPPORT_VALUES`` (schemas/claim_support.py) is the controlled vocabulary. It is also
re-typed by hand in the panel's JS, in the methods statement researchers paste into a
paper, and in the docs/skills that tell people what to pass to ``--value``. Those copies
drift silently: ``overstated`` was missing from four of them at once, so the generated
methods paragraph misdescribed the instrument that had actually been used, and the Atlas
coloured overclaims by an undeclared fallback.

This file is the sync gate. Add a value to SUPPORT_VALUES and these tests name every
surface that still has to learn about it — a failure here is a to-do list, not a bug.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import citevahti
from citevahti.report import methods
from citevahti.schemas.claim_support import SUPPORT_DEFINITIONS, SUPPORT_VALUES
from citevahti.state import CiteVahtiStore

WEB = Path(citevahti.__file__).parent / "panel" / "web"
REPO = Path(__file__).resolve().parents[1]


def _block(text: str, opener: str, closer: str) -> str:
    """The source between ``opener`` and the next ``closer`` — fails loudly if renamed."""
    start = text.index(opener) + len(opener)
    return text[start:text.index(closer, start)]


# --------------------------------------------------------------------------- Python


def test_definitions_cover_every_value():
    assert tuple(SUPPORT_DEFINITIONS) == SUPPORT_VALUES


# ------------------------------------------------------------------------ panel JS


def test_state_js_support_list_matches_the_python_tuple():
    src = (WEB / "state.js").read_text(encoding="utf-8")
    rows = _block(src, "const SUPPORT = [", "\n];")
    values = tuple(re.findall(r'\[\s*"([a-z_]+)"', rows))
    assert values == SUPPORT_VALUES, "panel/web/state.js SUPPORT drifted from SUPPORT_VALUES"


def test_state_js_labels_and_definitions_are_complete():
    # Every value needs a human label + a one-line definition, or the rating UI shows
    # a raw enum to the rater.
    src = (WEB / "state.js").read_text(encoding="utf-8")
    rows = _block(src, "const SUPPORT = [", "\n];")
    triples = re.findall(r'\[\s*"([a-z_]+)",\s*"([^"]+)",\s*"([^"]+)"\s*\]', rows)
    assert tuple(v for v, _, _ in triples) == SUPPORT_VALUES


def test_evidence_map_declares_a_hue_family_for_every_value():
    # A missing key falls through to `|| "review"` at the call site — the value would
    # still render, just silently mis-coloured. Declare, never default.
    src = (WEB / "evidence-map.js").read_text(encoding="utf-8")
    body = _block(src, "const EM_SUPPORT_VERDICT = {", "};")
    keys = set(re.findall(r"([a-z_]+)\s*:", body))
    assert keys == set(SUPPORT_VALUES), "panel/web/evidence-map.js EM_SUPPORT_VERDICT drifted"


def test_evidence_map_hue_families_are_real_verdicts():
    src = (WEB / "evidence-map.js").read_text(encoding="utf-8")
    order = _block(src, "const EM_ORDER = [", "];")
    families = set(re.findall(r'"([a-z]+)"', order))
    body = _block(src, "const EM_SUPPORT_VERDICT = {", "};")
    assert set(re.findall(r':\s*"([a-z]+)"', body)) <= families


def test_overstated_never_shares_the_hue_family_of_an_accept():
    # An overclaim cannot back an accept (schemas/decision.SUPPORTING_VALUES), so it must
    # not be drawn in the accept / accepted-with-caution families.
    from citevahti.schemas.decision import SUPPORTING_VALUES

    assert "overstated" not in SUPPORTING_VALUES
    src = (WEB / "evidence-map.js").read_text(encoding="utf-8")
    body = _block(src, "const EM_SUPPORT_VERDICT = {", "};")
    family = dict(re.findall(r'([a-z_]+)\s*:\s*"([a-z]+)"', body))
    assert family["overstated"] not in ("accept", "caution")


# ------------------------------------------------------- the pasted methods statement


def test_methods_statement_spells_out_the_whole_scale(tmp_path):
    # This paragraph goes into a manuscript's methods section: naming a subset of the
    # scale misdescribes the instrument the raters used.
    store = CiteVahtiStore(tmp_path)
    store.init()
    md = methods.build_methods_markdown(store)
    scale = _block(md, "(scale: ", ")")
    assert tuple(v.strip() for v in scale.split("/")) == SUPPORT_VALUES


def test_methods_template_does_not_hardcode_the_scale():
    assert "{scale}" in methods._TEMPLATE
    for value in SUPPORT_VALUES:
        assert value not in methods._TEMPLATE


# ------------------------------------------------------------------ prose duplicates

# Hand-maintained prose copies: (path, the phrase that opens the enumeration). The window
# after the phrase must name every value. Paths outside the package are skipped when
# absent, so the suite still passes when run against an installed wheel.
PROSE = [
    ("docs/REPORTING.md", "(scale: "),
    ("docs/CLI.md", "Support vocabulary:"),
    ("skills/citevahti-dev/citevahti-commands.md", "# values:"),
    ("skills/citevahti-dev/citevahti-commands.md", "## Support-rating values (`--value`)"),
]


@pytest.mark.parametrize("rel,opener", PROSE, ids=[f"{p}:{o[:24]}" for p, o in PROSE])
def test_prose_copies_list_every_support_value(rel, opener):
    path = REPO / rel
    if not path.exists():
        pytest.skip(f"{rel} not present (installed wheel, not a checkout)")
    text = path.read_text(encoding="utf-8")
    assert opener in text, f"{rel}: the enumeration opener {opener!r} was renamed"
    window = text[text.index(opener):text.index(opener) + len(opener) + 400]
    missing = [v for v in SUPPORT_VALUES if v not in window]
    assert not missing, f"{rel} omits {missing} from the support vocabulary"
