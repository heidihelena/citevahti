"""The claim-test vocabulary is stable (findings + state labels).

These labels are a cross-surface contract (MCP prompt, report, docs, UI). If the
set drifts, downstream copy and tooling silently disagree — so the membership is
pinned here. Add labels deliberately; do not repurpose existing ones.
"""

from citevahti import findings
from citevahti.schemas.claim_support import SUPPORT_VALUES
from citevahti.schemas.report import STATE_LABEL


def test_finding_labels_are_exactly_this_set():
    assert set(findings.FINDING_LABELS) == {
        "support_direct", "support_partial", "related_but_insufficient", "missing_support",
        "reference_broken", "reference_hallucinated", "reference_real_but_wrong",
        "population_mismatch", "intervention_mismatch", "comparator_mismatch",
        "outcome_mismatch", "study_design_mismatch", "overclaim", "needs_full_text",
        "candidate_found", "zotero_action_ready", "zotero_write_committed", "zotero_write_undone",
    }
    assert len(findings.FINDING_LABELS) == len(set(findings.FINDING_LABELS))   # no dupes


def test_state_labels_are_stable():
    assert STATE_LABEL == {
        "verified": "verified", "needs_support": "needs support",
        "review_needed": "review needed", "decision_recorded": "decided",
    }


def test_every_support_value_maps_to_a_real_finding():
    for v in SUPPORT_VALUES:
        f = findings.support_to_finding(v)
        assert f is not None and findings.is_finding(f)


def test_support_to_finding_examples():
    assert findings.support_to_finding("directly_supports") == "support_direct"
    assert findings.support_to_finding("does_not_support") == "missing_support"
    assert findings.support_to_finding("contradicts") == "reference_real_but_wrong"
    assert findings.support_to_finding("nonsense") is None
