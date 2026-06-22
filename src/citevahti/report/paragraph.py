"""Check-a-paragraph — the everyday, in-the-writing companion loop.

A PhD student writes a paragraph and wants to know, right now, which of its claims
they've already vetted, which need attention, and which are new — without setting up
a whole-manuscript review. This matches each sentence against the claims already in
the ledger (exact normalized hash, then substring / token-overlap) and reports its
status. Read-only; no AI, no network — it reuses the existing report + risk triage.
"""

from __future__ import annotations

from ..retrieval.text import coverage_score, segment_sentences
from ..risk.triage import triage
from ..schemas.report import ParagraphCheck, ParagraphSentence
from ..util import claim_text_hash, normalize_claim_text
from .claim_report import ClaimReportService

_MIN_LEN = 12          # ignore trivial fragments ("See Fig 1.", headings)
_FUZZY = 0.85          # token-coverage threshold for a fuzzy claim↔sentence match


def check_paragraph(store, text: str) -> ParagraphCheck:
    report = ClaimReportService(store).report()
    attn = {it.claim_id: it for it in triage(report).items}     # claim_id -> triage item
    by_hash = {claim_text_hash(r.claim_text): r for r in report.rows}
    norm_claims = [(normalize_claim_text(r.claim_text), r) for r in report.rows]

    out: list[ParagraphSentence] = []
    for _start, _end, sent in segment_sentences(text):
        norm = normalize_claim_text(sent)
        if len(norm) < _MIN_LEN:
            continue
        row = by_hash.get(claim_text_hash(sent))
        if row is None:                                         # fuzzy: substring or overlap
            for n, r in norm_claims:
                if n and (n in norm or norm in n or coverage_score(n, sent) >= _FUZZY):
                    row = r
                    break
        if row is None:
            out.append(ParagraphSentence(text=sent.strip(), status="new"))
            continue
        it = attn.get(row.claim_id)
        if it is None:                                          # matched, nothing to do
            out.append(ParagraphSentence(text=sent.strip(), claim_id=row.claim_id,
                                         state=row.state, status="reviewed"))
        else:
            out.append(ParagraphSentence(text=sent.strip(), claim_id=row.claim_id,
                                         state=row.state, status="attention",
                                         reason=it.reason, action=it.action))
    return ParagraphCheck(
        total=len(out),
        reviewed=sum(1 for s in out if s.status == "reviewed"),
        attention=sum(1 for s in out if s.status == "attention"),
        new=sum(1 for s in out if s.status == "new"),
        sentences=out)
