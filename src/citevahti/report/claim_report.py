"""ClaimReportService — run citation-integrity "tests" over a project's claims.

For each claim it derives one of four states from the ledger (candidates, blinded
support ratings, final decisions). It is strictly read-only: no new judgments, no
mutation, no Zotero or network calls. It is the data behind both the inline
VS Code review layer and the editor-mode Citation-Integrity Report.
"""

from __future__ import annotations

from typing import Optional

from ..schemas.report import (STATE_CODE, ClaimEvidence, ClaimReport,
                              ClaimReportRow, ReportProvenance)
from ..state.store import StateError
from ..util import utc_now_iso

RETRACTION_SOURCE = ("OpenAlex is_retracted, matched by DOI/PMID only — "
                     "items without a DOI or PMID are not checked")

_ACCEPTING = ("accept", "accepted_with_caution")
_FIT_FIELDS = ("population_fit", "intervention_fit", "outcome_fit", "claim_fit")


def _fit_total(fit) -> Optional[int]:
    """Sum the PICO + claim fit subscores (each 0..2) → 0..8. None if all unset."""
    vals = [getattr(fit, f, None) for f in _FIT_FIELDS]
    if all(v is None for v in vals):
        return None
    return sum(v or 0 for v in vals)


class ClaimReportService:
    def __init__(self, store) -> None:
        self.store = store

    def _candidates(self, claim_id: str):
        try:
            return self.store.load_candidates(claim_id).candidates
        except StateError:
            return []

    def _decision_for(self, candidate_id: str):
        try:
            return self.store.load_decision(f"dec-{candidate_id}")
        except StateError:
            return None

    def _ratings_index(self):
        # A pair can have more than one rating on disk (support_start mints a new id each
        # call); pick the most advanced/recent one deterministically — not an arbitrary
        # uuid-sorted one. (The old code used setdefault: "last wins" was a lie; the first
        # in uuid order won.)
        from ..claims.support import rating_preference_key

        idx: dict = {}
        for rid in self.store.list_support_ratings():
            r = self.store.load_support_rating(rid)
            key = (r.claim_id, r.candidate_id)
            if key not in idx or rating_preference_key(r) > rating_preference_key(idx[key]):
                idx[key] = r
        return idx

    @staticmethod
    def _unresolved_discordance(rating) -> bool:
        return bool(rating and rating.comparison.status == "discordant"
                    and rating.adjudication.final_value is None)

    def _row(self, claim, ratings_idx) -> ClaimReportRow:
        cands = self._candidates(claim.claim_id)
        evidence, has_accept, has_review, decided = [], False, False, 0
        for c in cands:
            dec = self._decision_for(c.candidate_id)
            rating = ratings_idx.get((claim.claim_id, c.candidate_id))
            if dec is not None:
                decided += 1
                if dec.final_decision in _ACCEPTING:
                    has_accept = True
                if dec.final_decision == "needs_second_review":
                    has_review = True
            if self._unresolved_discordance(rating):
                has_review = True
            human = rating.human_rating if (rating and rating.human_rating) else None
            human_v = human.value if human else None
            ai_raw = rating.ai_rating.value if (rating and rating.ai_rating) else None
            # blinded for the human card: the AI value is hidden until the human rates
            ai_blinded = ai_raw if human_v is not None else ("hidden" if ai_raw is not None else None)
            support = (dec.final_support_status if dec else None) or human_v
            # PICO fit + excerpt come ONLY from the human rating (never the blinded
            # AI), and only once committed — so the card can't leak the AI view.
            fit = human.fit if (human and human_v is not None) else None
            quote = next((p.quote for p in human.source_passages), None) \
                if (human and human_v is not None) else None
            evidence.append(ClaimEvidence(
                candidate_id=c.candidate_id,
                decision_id=(dec.decision_id if dec else None),
                rating_id=(rating.rating_id if rating else None),
                pmid=c.pmid, doi=c.doi, title=c.title, support_status=support,
                human_support=human_v, ai_support=ai_blinded,
                final_decision=(dec.final_decision if dec else None),
                agreement=(dec.agreement_status if dec else None),
                fit=fit, fit_total=_fit_total(fit) if fit else None, excerpt=quote,
                retracted=c.retracted))

        untestable = getattr(claim, "untestable_reason", None)
        if has_accept:
            state = "accepted"
        elif has_review:
            state = "review_needed"
        elif untestable:
            # The human declared the cited source out of indexed scope; absence
            # of indexed evidence must not masquerade as a failing claim. Real
            # work (accepted evidence / unresolved review) still wins above.
            state = "untestable"
        elif cands and decided == len(cands):
            state = "decision_recorded"            # all settled, none accepted
        else:
            state = "needs_support"                # no candidates, or undecided ones
        return ClaimReportRow(
            claim_id=claim.claim_id, claim_text=claim.claim_text, claim_type=claim.claim_type,
            manuscript_location=claim.manuscript_location, state=state, code=STATE_CODE[state],
            candidate_count=len(cands),
            accepted_count=sum(1 for e in evidence if e.final_decision in _ACCEPTING),
            evidence=evidence,
            proposed_revision=claim.proposed_revision,
            proposed_revision_by=claim.proposed_revision_by,
            untestable_reason=untestable)

    def _provenance(self) -> ReportProvenance:
        """Bind the report to the ledger state it was generated from: audit head,
        chain length/intactness, the full-ledger claim count (the completeness
        denominator), and when retractions were last scanned. Read-only."""
        audit = getattr(self.store, "audit", None)
        head = entries_n = intact = last_scan = None
        if audit is not None:
            entries = audit.entries()
            entries_n = len(entries)
            head = entries[-1].hash if entries else None
            intact = audit.verify()
            last_scan = next((e.ts for e in reversed(entries)
                              if e.event == "retraction.scan"), None)
        return ReportProvenance(
            audit_head_hash=head, audit_entries=entries_n, audit_chain_intact=intact,
            ledger_claims_total=len(self.store.list_claims()),
            last_retraction_scan_at=last_scan, retraction_source=RETRACTION_SOURCE)

    def report(self, claim_ids: Optional[list[str]] = None) -> ClaimReport:
        ratings_idx = self._ratings_index()
        ids = claim_ids if claim_ids is not None else self.store.list_claims()
        rows = [self._row(self.store.load_claim(cid), ratings_idx) for cid in ids]
        counts = {s: 0 for s in ("accepted", "needs_support", "review_needed",
                                 "decision_recorded", "untestable")}
        for r in rows:
            counts[r.state] += 1
        return ClaimReport(generated_at=utc_now_iso(), total=len(rows), counts=counts,
                           rows=rows, provenance=self._provenance())
