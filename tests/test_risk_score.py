"""Epistemic Risk Score: invariants for a trust-infrastructure number.

The score must be provably the right direction (monotone in severity),
non-compensatory (one fatal item cannot be averaged away), coverage-aware,
bounded, and deterministic.
"""

from citevahti.risk import score_report
from citevahti.schemas.report import STATE_CODE, ClaimEvidence, ClaimReport, ClaimReportRow


def ev(support=None, decision=None, retracted=None, fit_total=None, cid="c1"):
    return ClaimEvidence(candidate_id=cid, support_status=support,
                         final_decision=decision, retracted=retracted, fit_total=fit_total)


def row(cid, state, loc="Discussion p1", ctype=None, evidence=()):
    return ClaimReportRow(claim_id=cid, claim_text=f"claim {cid}", claim_type=ctype,
                          manuscript_location=loc, state=state, code=STATE_CODE[state],
                          evidence=list(evidence))


def report(rows):
    return ClaimReport(generated_at="2026-06-16T00:00:00+00:00", total=len(rows), rows=rows)


def _accepted(cid="a", **kw):
    return row(cid, "accepted", evidence=[ev("directly_supports", "accept")], **kw)


def test_clean_manuscript_scores_zero():
    rep = score_report(report([_accepted(cid=f"a{i}") for i in range(5)]))
    assert rep.score == 0
    assert rep.band == "low"
    assert 0 <= rep.score <= 100


def test_monotone_in_severity():
    clean = [_accepted(cid=f"a{i}") for i in range(5)]
    base = score_report(report(clean)).score
    worse = list(clean)
    worse[0] = row("a0", "decision_recorded", evidence=[ev("contradicts", "reject")])
    assert score_report(report(worse)).score > base


def test_noncompensatory_retraction_floor():
    rows = [_accepted(cid=f"a{i}") for i in range(9)]
    # one accepted claim resting on a retracted source — fatal, must set a floor
    rows.append(row("bad", "accepted", loc="Conclusion",
                    evidence=[ev("directly_supports", "accept", retracted=True)]))
    rep = score_report(report(rows))
    assert rep.score >= 70                       # not diluted by the 9 clean claims
    assert rep.score_low >= 70                    # the floor pins the lower band too
    assert any(c.fatal for c in rep.top_contributors)


def test_low_coverage_is_flagged():
    rep = score_report(report([row(f"n{i}", "needs_support") for i in range(8)]))
    assert rep.band == "insufficient_coverage"
    assert rep.coverage < 0.5


def test_more_coverage_does_not_auto_worsen():
    # Adding *tested, clean* claims raises coverage and must not increase risk.
    few = report([row("n0", "needs_support")] + [_accepted(cid=f"a{i}") for i in range(2)])
    many = report([row("n0", "needs_support")] + [_accepted(cid=f"a{i}") for i in range(20)])
    assert score_report(many).coverage > score_report(few).coverage
    assert score_report(many).score <= score_report(few).score


def test_untestable_excluded_from_denominator():
    rep = score_report(report([row("u", "untestable"), _accepted()]))
    assert rep.n_testable == 1
    assert rep.n_claims == 2


def test_salience_orders_same_verdict():
    concl = report([row("x", "decision_recorded", loc="Conclusion",
                        evidence=[ev("contradicts", "reject")])])
    bg = report([row("x", "decision_recorded", loc="Background", ctype="background",
                     evidence=[ev("contradicts", "reject")])])
    assert score_report(concl).score > score_report(bg).score


def test_salience_override_hook():
    r = report([row("x", "decision_recorded", loc="Background", ctype="background",
                    evidence=[ev("contradicts", "reject")])])
    low = score_report(r).score
    high = score_report(r, salience_map={"x": 1.0}).score
    assert high > low


def test_overstated_severity_between_partial_and_does_not_support():
    # 'overstated' (claim says more than the evidence supports) is a real failure:
    # heavier than partial support, lighter than no support / contradiction.
    def s(support):
        return score_report(report([row("x", "review_needed", loc="Conclusion",
                                        evidence=[ev(support, "needs_second_review")])])).score
    assert s("partially_supports") < s("overstated") < s("does_not_support")


def test_bounded_and_deterministic():
    rows = [row("a", "accepted", evidence=[ev("partially_supports", "accepted_with_caution",
                                              fit_total=2)]),
            row("b", "decision_recorded", loc="Conclusion", evidence=[ev("contradicts", "reject")]),
            row("u", "untestable")]
    r = report(rows)
    a, b = score_report(r), score_report(r)
    da, db = a.model_dump(), b.model_dump()
    da.pop("generated_at"); db.pop("generated_at")   # wall-clock stamp differs by design
    assert da == db
    assert 0 <= a.score <= 100
    assert a.score_low <= a.score <= a.score_high
