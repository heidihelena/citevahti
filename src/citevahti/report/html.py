"""Render the citation-integrity report as a standalone, print-friendly HTML page.

Same content as the Markdown export, built from the structured ``ClaimReport`` (no
markdown parsing). It is what the panel opens for **Save as PDF** via the browser's
print dialog — zero dependencies, fully offline. Read-only; asserts no truth.
"""

from __future__ import annotations

from html import escape as _e

from ..schemas.report import STATE_CODE, ClaimReport, ClaimReportRow

_STATE_TITLE = {
    "accepted": "Accepted", "needs_support": "Needs support",
    "review_needed": "Review needed", "decision_recorded": "Decision recorded",
    "untestable": "Untestable (out of indexed scope)",
}
_ORDER = ("needs_support", "review_needed", "decision_recorded", "accepted", "untestable")

_STYLE = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;max-width:760px;
  margin:24px auto;padding:0 18px;color:#1A1A1F;line-height:1.55}
h1{font-size:22px}h2{font-size:14px;text-transform:uppercase;letter-spacing:.6px;color:#6B4E9E;margin-top:26px}
h3{font-size:15px;margin:16px 0 4px}
table{border-collapse:collapse;font-size:13px;margin:8px 0}th,td{border:1px solid #E2E2E7;padding:5px 9px;text-align:left}
.muted{color:#6B6B73;font-size:13px}.warn{color:#7A1F45;font-weight:600}
ul{margin:4px 0 4px 2px;padding-left:18px}li{margin:4px 0}
.code{font:600 11px/1 ui-monospace,Menlo,monospace;color:#6B4E9E}
.foot{margin-top:28px;border-top:1px solid #E2E2E7;padding-top:12px;font-size:12.5px;color:#5B5570}
@media print{body{margin:0}a{color:inherit;text-decoration:none}}
"""


def _evidence_html(row: ClaimReportRow) -> str:
    items = []
    for e in row.evidence:
        ids = " · ".join(p for p in (f"PMID {e.pmid}" if e.pmid else "",
                                     f"DOI {e.doi}" if e.doi else "") if p)
        human = _e(e.human_support or "—")
        ai = "hidden (blinded)" if e.ai_support == "hidden" else _e(e.ai_support or "—")
        dec = f" · decision: <b>{_e(e.final_decision)}</b>" if e.final_decision else ""
        flag = ' — <span class="warn">⚠ RETRACTED</span>' if e.retracted else ""
        meta = f" — {_e(ids)}" if ids else ""
        items.append(f"<li><b>{_e(e.title or '(untitled)')}</b>{flag}{meta}<br>"
                     f'<span class="muted">human: {human} · AI: {ai}{dec}</span></li>')
    if not items:
        items.append('<li class="muted">no candidate evidence linked yet</li>')
    return "<ul>" + "".join(items) + "</ul>"


def _claim_html(row: ClaimReportRow) -> str:
    code = STATE_CODE[row.state].strip()
    parts = [f"<h3><span class='code'>[{_e(code)}]</span> {_e(_STATE_TITLE[row.state])} — {_e(row.claim_text)}</h3>"]
    if row.manuscript_location:
        parts.append(f'<div class="muted">Location: {_e(row.manuscript_location)}</div>')
    if row.state == "untestable" and row.untestable_reason:
        parts.append(f'<div class="muted">Out of indexed scope: {_e(row.untestable_reason)}</div>')
    if row.proposed_revision:
        by = _e(row.proposed_revision_by or "human")
        parts.append(f'<div class="muted">Pending revision ({by}-proposed): '
                     f"<i>{_e(row.proposed_revision)}</i></div>")
    parts.append(_evidence_html(row))
    return "".join(parts)


def render_html(report: ClaimReport, *, title: str = "Citation-Integrity Report") -> str:
    c = report.counts
    needs = c.get("needs_support", 0) + c.get("review_needed", 0)
    retracted = sum(1 for r in report.rows for e in r.evidence if e.retracted)
    counts_rows = "".join(
        f"<tr><td>{_e(lbl)}</td><td>{c.get(k, 0)}</td></tr>" for k, lbl in (
            ("accepted", "✓ Accepted (supported citation)"), ("needs_support", "Needs support"),
            ("review_needed", "Review needed"), ("decision_recorded", "Decision recorded"),
            ("untestable", "Untestable (out of indexed scope)")))
    alerts = ""
    if needs:
        alerts += f"<p><b>{needs} claim(s) need attention</b> (no accepted evidence, or an unresolved human/AI disagreement).</p>"
    if retracted:
        alerts += (f'<p class="warn">⚠ {retracted} linked candidate(s) are flagged as retracted — '
                   "re-check any claim that cites them.</p>")
    sections = ""
    for state in _ORDER:
        rows = [r for r in report.rows if r.state == state]
        if rows:
            sections += f"<h2>{_e(_STATE_TITLE[state])}</h2>" + "".join(_claim_html(r) for r in rows)

    p = report.provenance
    foot = ['<div class="foot"><b>Scope &amp; limitations</b><ul>']
    if p is not None and p.ledger_claims_total is not None:
        foot.append(f"<li><b>Coverage:</b> {report.total} of {p.ledger_claims_total} ledger claim(s). "
                    "Claims enter the ledger only when the author adds them.</li>")
    else:
        foot.append(f"<li><b>Coverage:</b> {report.total} claim(s), as entered by the author.</li>")
    if p is not None and p.audit_entries is not None:
        intact = "intact" if p.audit_chain_intact else "<b>BROKEN</b>"
        foot.append(f"<li><b>Integrity:</b> audit chain of {p.audit_entries} entries, head "
                    f"<span class='code'>{_e((p.audit_head_hash or '')[:16])}…</span>, {intact} at generation "
                    "(tamper-evident, not forgery-proof).</li>")
    if p is not None:
        foot.append(f"<li><b>Retractions:</b> via {_e(p.retraction_source or 'OpenAlex')}; "
                    f"last scan {_e(p.last_retraction_scan_at or 'never')}. Absence of a flag is not proof.</li>")
    foot.append("<li><b>Meaning of verdicts:</b> citation support from the blinded human → AI → "
                "adjudication workflow — not clinical or scientific truth.</li></ul></div>")

    return (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{_e(title)}</title><style>{_STYLE}</style></head><body>"
            f"<h1>{_e(title)}</h1>"
            f'<p class="muted">Generated {_e(report.generated_at)} · {report.total} claim(s) tested.</p>'
            f"<table><tr><th>State</th><th>Count</th></tr>{counts_rows}</table>"
            f"{alerts}{sections}{''.join(foot)}</body></html>")
