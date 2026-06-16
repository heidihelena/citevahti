"""Epistemic Risk Score — a derived, advisory, read-only triage number.

Pure function of a ``ClaimReport`` (the same artifact the inline reviewer and the
Citation-Integrity Report already produce). It makes NO new judgments, touches no
store, and performs no network calls. The output triages an editor's attention; it
is never a pass/fail gate, and the per-claim contributions are always shown with it.

How it scores (rule-based v0, uncalibrated — see docstring of ``schemas/risk.py``):

  per-claim   risk_i = severity(verdict, state) x salience(location, type) x exposure(retraction)
  manuscript  base   = power_mean(risk_i, p=3)            # non-compensatory: worst claims dominate
              score  = max(base, fatal_floor) x 100       # an accepted-on-retracted claim sets a floor
              band   = coverage-aware (low / moderate / high / insufficient_coverage)

The single tunable, ``p``, interpolates the aggregate between the mean (p=1) and the
worst case (p=inf); p=3 makes risk "super-additive in severity" without collapsing to
a pure max. That is the deliberate alternative to six hand-picked dimension weights.
"""

from __future__ import annotations

from typing import Mapping, Optional

from ..schemas.report import ClaimReport, ClaimReportRow
from ..schemas.risk import (ClaimRiskContribution, EpistemicRiskReport,
                            RiskSubscores)
from ..util import utc_now_iso

# Decided final-decision values that count as "accepted supporting evidence".
_ACCEPTING = ("accept", "accepted_with_caution")

# How badly each support verdict fails to support the claim (0 = perfect, 1 = fatal).
_SEVERITY_BY_SUPPORT = {
    "contradicts": 1.00,
    "does_not_support": 0.85,
    "overstated": 0.70,          # cited paper supports a *weaker* claim than the one made
    "unclear": 0.50,
    "indirectly_supports": 0.35,
    "partially_supports": 0.30,
    "directly_supports": 0.00,
}
# Fallback severity from the claim's derived state when no per-pair verdict drives it.
_SEVERITY_BY_STATE = {
    "accepted": 0.00,            # has accepted, supporting evidence
    "needs_support": 0.60,       # asserted, but no accepted support recorded
    "review_needed": 0.45,       # unresolved human/AI discordance
    "decision_recorded": 0.70,   # every candidate settled, none accepted
}
_NEGATIVE = ("contradicts", "does_not_support")
_POWER = 3.0
_RETRACTION_BOOST = 1.5          # exposure multiplier when a retracted source is in play
_COVERAGE_FLOOR = 0.50          # below this, the band is flagged 'insufficient_coverage'


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def _salience(row: ClaimReportRow, override: Optional[Mapping[str, float]]) -> float:
    """How central the claim is to the manuscript's argument (0..1).

    A transparent location/type heuristic by default; pass ``salience_map`` to inject
    a better signal (e.g. EpiNet node-centrality in the claim-support graph)."""
    if override is not None and row.claim_id in override:
        return _clamp(float(override[row.claim_id]))
    loc = (row.manuscript_location or "").lower()
    if any(k in loc for k in ("conclusion", "abstract", "summary")):
        base = 1.00
    elif any(k in loc for k in ("result", "discussion")):
        base = 0.70
    elif any(k in loc for k in ("introduction", "background", "method")):
        base = 0.40
    else:
        base = 0.60
    ctype = (row.claim_type or "").lower()
    if ctype == "background":
        base = min(base, 0.40)
    elif ctype in ("guideline_recommendation", "effectiveness", "diagnostic_accuracy",
                   "prognosis", "risk_factor"):
        base = max(base, 0.60)
    return _clamp(base, 0.10, 1.00)


def _row_signals(row: ClaimReportRow):
    """Return (severity, retracted_in_play, accepted_on_retracted, negative_support)."""
    ev = row.evidence
    accepted = [e for e in ev if (e.final_decision or "") in _ACCEPTING]
    supports = [e.support_status for e in ev if e.support_status]
    negative = any(s in _NEGATIVE for s in supports)
    retracted_in_play = any(bool(e.retracted) for e in ev)
    accepted_on_retracted = any(bool(e.retracted) for e in accepted)

    if row.state == "accepted":
        # Residual risk from the *best* accepting verdict (caution/partial leaves a little).
        sevs = [_SEVERITY_BY_SUPPORT.get(e.support_status or "", 0.0) for e in accepted] or [0.0]
        severity = min(sevs)
    else:
        neg_sev = [_SEVERITY_BY_SUPPORT.get(s, 0.0) for s in supports]
        severity = max([_SEVERITY_BY_STATE.get(row.state, 0.50)] + neg_sev)
    return severity, retracted_in_play, accepted_on_retracted, negative


def _is_tested(row: ClaimReportRow) -> bool:
    if row.state in ("accepted", "decision_recorded", "review_needed"):
        return True
    return any((e.human_support or e.final_decision) for e in row.evidence)


def score_report(report: ClaimReport, *, salience_map: Optional[Mapping[str, float]] = None,
                 p: float = _POWER) -> EpistemicRiskReport:
    rows = report.rows
    testable = [r for r in rows if r.state != "untestable"]
    n_testable = len(testable)
    contributions: list[ClaimRiskContribution] = []

    fatal_floor = 0.0
    tested = 0
    n_unsupported = n_contradiction = n_retraction = n_disagree = 0
    n_accepted = n_weak_fit = 0

    for row in testable:
        severity, retracted, accepted_on_retracted, negative = _row_signals(row)
        salience = _salience(row, salience_map)
        mult = _RETRACTION_BOOST if retracted else 1.0
        risk = _clamp(severity * salience * mult)

        fatal = accepted_on_retracted or (severity >= 1.0 and salience >= 0.80)
        if fatal:
            fatal_floor = max(fatal_floor, 0.70 if accepted_on_retracted else 0.60)

        if _is_tested(row):
            tested += 1
        if row.state in ("needs_support", "decision_recorded"):
            n_unsupported += 1
        if negative:
            n_contradiction += 1
        if retracted:
            n_retraction += 1
        if row.state == "review_needed":
            n_disagree += 1
        if row.state == "accepted":
            n_accepted += 1
            ft = next((e.fit_total for e in row.evidence
                       if (e.final_decision or "") in _ACCEPTING and e.fit_total is not None), None)
            if ft is not None and ft < 4:   # weak PICO/claim fit behind a 'supported' claim
                n_weak_fit += 1

        contributions.append(ClaimRiskContribution(
            claim_id=row.claim_id, claim_text=(row.claim_text[:160] if row.claim_text else None),
            state=row.state, support_status=next((e.support_status for e in row.evidence
                                                  if e.support_status), None),
            salience=round(salience, 3), severity=round(severity, 3),
            retracted=retracted, fatal=fatal, risk=round(risk, 3)))

    risks = [c.risk for c in contributions]
    if risks:
        base = (sum(r ** p for r in risks) / len(risks)) ** (1.0 / p)
    else:
        base = 0.0
    base = max(base, fatal_floor)
    score = round(base * 100)

    coverage = (tested / n_testable) if n_testable else 0.0
    # Uncertainty band widens as coverage drops and for small claim counts.
    half = min(50, round((1.0 - coverage) * 55 + (8.0 / max(n_testable, 1)) * 8))
    score_low = max(0, score - half, round(fatal_floor * 100))
    score_high = min(100, score + half)

    if coverage < _COVERAGE_FLOOR:
        band = "insufficient_coverage"
    elif score >= 50:
        band = "high"
    elif score >= 20:
        band = "moderate"
    else:
        band = "low"

    def share(n: int) -> float:
        return round(n / n_testable, 3) if n_testable else 0.0

    sub = RiskSubscores(
        unsupported_share=share(n_unsupported),
        contradiction_risk=share(n_contradiction),
        retraction_exposure=share(n_retraction),
        disagreement_risk=share(n_disagree),
        fit_risk=(round(n_weak_fit / n_accepted, 3) if n_accepted else 0.0),
    )

    caveats = [
        "Advisory triage only — not a pass/fail gate; read the per-claim contributions.",
        "Rule-based v0: severity/salience are documented defaults, not weights calibrated to outcomes.",
        "Retraction signal is only as complete as the underlying scan (DOI/PMID-matched).",
    ]
    if coverage < _COVERAGE_FLOOR:
        caveats.append(
            f"Insufficient coverage: only {tested}/{n_testable} testable claims have a recorded "
            "decision — the score is provisional and the band is widened accordingly.")
    if fatal_floor > 0.0:
        caveats.append(
            "A non-compensatory floor is active (an accepted claim resting on a retracted source, "
            "or a high-salience claim the evidence contradicts).")

    return EpistemicRiskReport(
        generated_at=utc_now_iso(),
        score=score, band=band, score_low=score_low, score_high=score_high,
        subscores=sub,
        n_claims=len(rows), n_testable=n_testable, n_tested=tested,
        coverage=round(coverage, 3),
        top_contributors=sorted(contributions, key=lambda c: c.risk, reverse=True)[:10],
        caveats=caveats,
    )
