"""Citation-on-copy support: the panel exposes an accepted claim's citation so the
front-end can attach it when a cited passage is copied (data-citation hook in app.js).

This guards the server half — `_claim_state` surfaces the accepted candidate's
identifiers, and only for an accepted, supporting decision.
"""

from citevahti.panel.server import _accepted_cite, _claim_state
from citevahti.schemas.report import ClaimEvidence, ClaimReportRow


def _row(state, code, evidence):
    return ClaimReportRow(claim_id="c1", claim_text="t", state=state, code=code,
                          candidate_count=len(evidence), accepted_count=0, evidence=evidence)


def test_accepted_claim_exposes_its_citation():
    ev = ClaimEvidence(candidate_id="cand-1", final_decision="accept",
                       title="Telephone follow-up after surgery", doi="10.1/x", pmid="30000004")
    out = _claim_state(_row("accepted", "oo", [ev]))
    assert out["cite"] == {"title": "Telephone follow-up after surgery", "doi": "10.1/x", "pmid": "30000004"}


def test_accepted_with_caution_also_counts_as_a_cited_passage():
    ev = ClaimEvidence(candidate_id="cand-1", final_decision="accepted_with_caution", doi="10.2/y")
    assert _accepted_cite(_row("accepted", "oo", [ev])) == {"title": None, "doi": "10.2/y", "pmid": None}


def test_rejected_or_pending_claims_carry_no_citation():
    rejected = ClaimEvidence(candidate_id="cand-1", final_decision="reject", doi="10.3/z")
    assert "cite" not in _claim_state(_row("decision_recorded", "d", [rejected]))
    pending = ClaimEvidence(candidate_id="cand-2", title="staged but undecided")
    assert "cite" not in _claim_state(_row("needs_support", "o", [pending]))


def test_accepted_without_any_identifier_is_skipped():
    # nothing to cite -> no data-citation; never emit an empty reference
    ev = ClaimEvidence(candidate_id="cand-1", final_decision="accept")
    assert _accepted_cite(_row("accepted", "oo", [ev])) is None
