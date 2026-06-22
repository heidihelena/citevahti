"""Risk-first triage — turn "review all your claims" into "here are the few worth
your attention, and what to do about each."

A PhD student finishing a draft will not blind-rate 84 citations. They will fix the
6 that could embarrass them. This reads the (already computed) per-claim risk and the
report state and, for each claim that needs attention, names the REASON in plain words
and a concrete next ACTION — ordered worst-first. Read-only; derived from the report +
:func:`citevahti.risk.score.score_report`.
"""

from __future__ import annotations

from typing import Optional

from ..schemas.report import ClaimReport, ClaimReportRow
from ..schemas.risk import EpistemicRiskReport, TriageItem, TriageReport
from .score import score_report

_ACCEPTING = ("accept", "accepted_with_caution")
_NEGATIVE = ("does_not_support", "contradicts")
_WEAK_FIT = 4               # fit_total (0..8) at or below this is a weak fit behind an accept


def _classify(row: ClaimReportRow) -> Optional[tuple[str, str]]:
    """(reason, action) for a claim that needs attention, or None when it's clean.

    Worst-first: a retracted/contradicted source outranks a wording fix, which outranks
    'no support yet'. One reason per claim — the most important one."""
    ev = row.evidence
    supports = [e.support_status for e in ev if e.support_status]
    accepted = [e for e in ev if (e.final_decision or "") in _ACCEPTING]

    if any(bool(e.retracted) for e in ev):
        return ("A retracted paper sits behind this claim.",
                "Replace the source (or mark the claim untestable) — don't cite a retraction.")
    if any((e.final_decision or "") in _ACCEPTING and (e.support_status in _NEGATIVE)
           for e in ev):
        return ("Accepted on evidence that does not actually support it.",
                "Re-rate or reject — the cited paper doesn't back this claim.")
    if "overstated" in supports:
        return ("Overstated — the cited paper supports a weaker version of this claim.",
                "Tighten the wording to match the evidence, then accept.")
    if row.state == "review_needed":
        return ("Raters disagree on whether the source supports it.",
                "Adjudicate the disagreement, or mark it for a second review.")
    if row.has_stale_bonds:
        return ("The claim was reworded after its citation was accepted.",
                "Re-rate the evidence against the new wording.")
    if row.state == "needs_support":
        return ("No accepted supporting citation yet.",
                "Find supporting evidence, or revise the claim to what you can support.")
    if row.state == "decision_recorded":
        return ("Decided, but no citation was accepted as supporting.",
                "Add a supporting source, or leave the claim uncited on purpose.")
    if row.state == "accepted":
        ft = next((e.fit_total for e in accepted if e.fit_total is not None), None)
        if ft is not None and ft <= _WEAK_FIT:
            return ("Accepted, but the PICO/claim fit is weak.",
                    "Double-check the source really fits the population/intervention/outcome.")
    return None


def triage(report: ClaimReport, risk: Optional[EpistemicRiskReport] = None) -> TriageReport:
    """The claims worth a researcher's attention, worst-first, each with reason + action."""
    risk = risk or score_report(report)
    risk_by_claim = {c.claim_id: c for c in risk.top_contributors}

    items: list[TriageItem] = []
    for row in report.rows:
        if row.state == "untestable":
            continue
        rc = _classify(row)
        if rc is None:
            continue
        reason, action = rc
        contrib = risk_by_claim.get(row.claim_id)
        items.append(TriageItem(
            claim_id=row.claim_id, claim_text=row.claim_text, state=row.state,
            reason=reason, action=action,
            risk=(contrib.risk if contrib else 0.0),
            fatal=(bool(contrib.fatal) if contrib else False)))
    # worst-first: fatal, then risk desc, then by claim text for stability
    items.sort(key=lambda i: (not i.fatal, -i.risk, i.claim_text or ""))
    clean = sum(1 for r in report.rows if r.state != "untestable") - len(items)
    return TriageReport(generated_at=risk.generated_at, total=report.total,
                        needs_attention=len(items), clean=max(0, clean),
                        score=risk.score, band=risk.band, items=items)
