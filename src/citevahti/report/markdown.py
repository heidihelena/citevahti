"""Render the citation-integrity report as a shareable Markdown document.

This is "editor mode": the read-only Citation-Integrity Report a supervisor,
journal editor, or guideline methodologist receives — no Zotero write, just the
claim-by-claim test results with provenance. It records the human → AI →
adjudication workflow; it does not assert truth.
"""

from __future__ import annotations

from ..findings import support_to_finding
from ..schemas.report import STATE_CODE, STATE_LABEL, ClaimReport, ClaimReportRow

_STATE_TITLE = {
    "accepted": "Accepted", "needs_support": "Needs support",
    "review_needed": "Review needed", "decision_recorded": "Decision recorded",
    "untestable": "Untestable (out of indexed scope)",
}


def _evidence_lines(row: ClaimReportRow) -> list[str]:
    out = []
    for e in row.evidence:
        ids = " · ".join(p for p in (f"PMID {e.pmid}" if e.pmid else "",
                                     f"DOI {e.doi}" if e.doi else "") if p)
        human = e.human_support or "—"
        ai = "hidden (blinded)" if e.ai_support == "hidden" else (e.ai_support or "—")
        dec = f" · decision: **{e.final_decision}**" if e.final_decision else ""
        flag = " — **⚠ RETRACTED**" if e.retracted else ""
        out.append(f"  - **{e.title or '(untitled)'}**{flag}"
                   + (f" — {ids}" if ids else "")
                   + f"  \n    human: {human} · AI: {ai}{dec}")
    if not out:
        out.append("  - _no candidate evidence linked yet_")
    return out


def _retracted_count(report: ClaimReport) -> int:
    return sum(1 for r in report.rows for e in r.evidence if e.retracted)


def _limitations_lines(report: ClaimReport) -> list[str]:
    """The scope-and-limitations footer every report carries (COPE-style: say
    what the artifact can and cannot vouch for, in the artifact itself)."""
    p = report.provenance
    lines = ["", "---", "", "**Scope & limitations** — read before relying on this report.", ""]
    if p is not None and p.ledger_claims_total is not None:
        lines.append(f"- **Coverage:** this report covers {report.total} of the "
                     f"{p.ledger_claims_total} claim(s) recorded in the ledger. Claims "
                     "enter the ledger only when the author adds them; the report cannot "
                     "certify that every claim in the manuscript was entered.")
    else:
        lines.append(f"- **Coverage:** {report.total} claim(s), as entered by the author. "
                     "The report cannot certify that every claim in the manuscript was entered.")
    if p is not None and p.audit_entries is not None:
        intact = "intact" if p.audit_chain_intact else "**BROKEN**"
        head = (p.audit_head_hash or "")[:16]
        lines.append(f"- **Integrity:** audit chain of {p.audit_entries} entries, "
                     f"head `{head}…`, {intact} at generation. The chain is "
                     "tamper-evident, not cryptographically signed: it shows the recorded "
                     "order of work, but a regenerated ledger would also validate. Treat it "
                     "as honest-researcher provenance, not forgery-proof certification.")
    if p is not None:
        scanned = p.last_retraction_scan_at or "never"
        lines.append(f"- **Retractions:** checked via {p.retraction_source or 'OpenAlex'}; "
                     f"last scan: {scanned}. Absence of a flag is not proof a work is "
                     "unretracted.")
    lines.append("- **Meaning of verdicts:** states record citation support as rated in the "
                 "blinded human → AI → adjudication workflow — not clinical or scientific truth.")
    return lines


def _claim_section(row: ClaimReportRow) -> str:
    code = STATE_CODE[row.state].strip()
    head = f"### [{code}] {_STATE_TITLE[row.state]} — {row.claim_text}"
    loc = f"- Location: {row.manuscript_location}\n" if row.manuscript_location else ""
    if row.state == "untestable":
        why = f": {row.untestable_reason}" if row.untestable_reason else ""
        loc += (f"- Out of indexed scope{why} — the cited source is not "
                "auto-checkable against PubMed/OpenAlex/Semantic Scholar; "
                "verify it against the source text directly.\n")
    rev = ""
    if row.proposed_revision:
        by = row.proposed_revision_by or "human"
        rev = (f"- Pending revision ({by}-proposed, not yet accepted):\n"
               f"  - was: {row.claim_text}\n  - now: {row.proposed_revision}\n")
    ev = "- Evidence:\n" + "\n".join(_evidence_lines(row))
    return f"{head}\n{loc}{rev}{ev}\n"


def render_markdown(report: ClaimReport, *, title: str = "Citation-Integrity Report") -> str:
    c = report.counts
    needs = c.get("needs_support", 0) + c.get("review_needed", 0)
    lines = [
        f"# {title}", "",
        f"_Generated {report.generated_at} · {report.total} claim(s) tested._", "",
        "| State | Count |", "|---|---:|",
        f"| ✓ Accepted (supported citation) | {c.get('accepted', 0)} |",
        f"| Needs support | {c.get('needs_support', 0)} |",
        f"| Review needed | {c.get('review_needed', 0)} |",
        f"| Decision recorded | {c.get('decision_recorded', 0)} |",
        f"| Untestable (out of indexed scope) | {c.get('untestable', 0)} |", "",
    ]
    if needs:
        lines.append(f"**{needs} claim(s) need attention** (no accepted evidence, or an "
                     "unresolved human/AI disagreement).")
        lines.append("")
    retracted = _retracted_count(report)
    if retracted:
        lines.append(f"**⚠ {retracted} linked candidate(s) are flagged as retracted** — "
                     "re-check any claim that cites them, whatever its state.")
        lines.append("")

    def block(heading: str, states: tuple) -> None:
        rows = [r for r in report.rows if r.state in states]
        if not rows:
            return
        lines.append(f"## {heading}")
        lines.append("")
        for r in rows:
            lines.append(_claim_section(r))

    block("Claims needing attention", ("needs_support", "review_needed"))
    block("Accepted claims", ("accepted",))
    block("Decisions recorded", ("decision_recorded",))
    block("Untestable claims (out of indexed scope — verify against the source directly)",
          ("untestable",))

    lines.extend(_limitations_lines(report))
    lines.append("")
    lines.append("_Produced by CiteVahti. Records the blinded human → AI → adjudication "
                 "workflow with provenance; it does not assert truth._")
    return "\n".join(lines) + "\n"


# --- the claim-test report (the "manuscript as code" framing) ----------------
def render_test_report(report: ClaimReport, *, title: str = "Claim Test Report") -> str:
    """Render the report as test results: a state-count summary, then per claim.

    Same data as ``render_markdown``, framed as a test run. Blinding holds: the AI
    rating is shown only once the human has rated (``ai_support`` is "hidden"
    otherwise), and the per-claim finding is derived only from the human value.
    """
    c = report.counts
    lines = [
        f"# {title}", "",
        f"_Generated {report.generated_at} · {report.total} claim(s) tested._", "",
        "## Summary", "",
        f"- `[oo]` {STATE_LABEL['accepted']}: {c.get('accepted', 0)}",
        f"- `[o]` {STATE_LABEL['needs_support']}: {c.get('needs_support', 0)}",
        f"- `[r]` {STATE_LABEL['review_needed']}: {c.get('review_needed', 0)}",
        f"- `[d]` {STATE_LABEL['decision_recorded']}: {c.get('decision_recorded', 0)}",
        f"- `[u]` {STATE_LABEL['untestable']}: {c.get('untestable', 0)}", "",
        "## Per claim", "",
    ]
    for row in report.rows:
        code = STATE_CODE[row.state].strip()
        lines.append(f"### `[{code}]` {STATE_LABEL[row.state]} — {row.claim_id}")
        lines.append(f"- Claim: {row.claim_text}")
        if row.manuscript_location:
            lines.append(f"- Location: {row.manuscript_location}")
        if row.state == "untestable":
            why = f" — {row.untestable_reason}" if row.untestable_reason else ""
            lines.append(f"- Out of indexed scope{why}: not auto-checkable against "
                         "the indexed literature; verify against the source directly.")
        if not row.evidence:
            if row.state != "untestable":
                lines.append("- Evidence candidate: _none linked yet_")
                lines.append(f"- Finding: `missing_support`")
        for e in row.evidence:
            ids = " · ".join(p for p in (f"PMID {e.pmid}" if e.pmid else "",
                                         f"DOI {e.doi}" if e.doi else "") if p)
            finding = support_to_finding(e.support_status) or "candidate_found"
            ai = "hidden (blinded until human rates)" if e.ai_support == "hidden" else (e.ai_support or "—")
            flag = " — **⚠ RETRACTED**" if e.retracted else ""
            lines.append(f"- Evidence candidate: {e.title or '(untitled)'}{flag}"
                         + (f" — {ids}" if ids else ""))
            lines.append(f"  - Finding: `{finding}`")
            lines.append(f"  - Human rating: {e.human_support or '—'}")
            lines.append(f"  - AI rating: {ai}")
            if e.fit_total is not None:
                lines.append(f"  - Citation fit: {e.fit_total}/8")
            if e.final_decision:
                lines.append(f"  - Final decision: **{e.final_decision}**")
        lines.append("")
    retracted = _retracted_count(report)
    if retracted:
        lines.append(f"**⚠ {retracted} linked candidate(s) are flagged as retracted.**")
    lines.extend(_limitations_lines(report))
    lines.append("")
    lines.append("_The human rates first; the AI second opinion stays blinded until then. "
                 "Zotero writes are previewed, confirmed, and undoable._")
    return "\n".join(lines) + "\n"
