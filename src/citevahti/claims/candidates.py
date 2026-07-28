"""CandidateService: link staged intake hits to a claim (ADR-0001, step 2).

This connects the spine (a claim) to the papers that entered consideration for
it, preserving *why each was found* (query, source, rank). It mutates no Zotero
state, asserts no support, and decides nothing. Candidates are de-duplicated per
claim by normalized PMID/DOI (never title-only), consistent with intake dedupe.
"""

from __future__ import annotations

from typing import Optional

from .. import __version__
from ..intake.dedupe import normalize_doi, normalize_pmid
from ..schemas.candidate import (
    CandidateLinkReport,
    CandidateMetadataDivergence,
    CandidateRepairReport,
    ClaimCandidates,
    ClaimPaperCandidate,
)
from ..schemas.common import Provenance
from ..state.store import StateError
from ..util import config_hash, sha256_hex, utc_now_iso

# The descriptive fields a re-imported record can correct. Identifiers are included
# because a match on one (say PMID) can still carry a different value for the other.
# `record_id`, `candidate_id` and the retrieval provenance are NOT here: they record how
# this paper entered consideration, which a later import does not get to rewrite.
REPAIRABLE_FIELDS = ("title", "journal", "year", "publication_date", "doi", "pmid", "abstract")


def _paper_key(pmid: Optional[str], doi: Optional[str], record_id: Optional[str]) -> str:
    np, nd = normalize_pmid(pmid), normalize_doi(doi)
    if np:
        return f"pmid:{np}"
    if nd:
        return f"doi:{nd}"
    return f"rec:{record_id or ''}"


def _as_text(value) -> Optional[str]:
    return None if value is None else str(value)


def _human_rated_count(store, claim_id: str, candidate_id: str) -> int:
    """How many of the pair's support ratings already carry a human judgement — i.e. how
    many people rated this paper as the record described it before the correction."""
    n = 0
    for rid in store.list_support_ratings():
        try:
            rec = store.load_support_rating(rid)
        except Exception:  # noqa: BLE001 (an unreadable rating must not block a repair)
            continue
        if (rec.claim_id == claim_id and rec.candidate_id == candidate_id
                and rec.human_rating is not None):
            n += 1
    return n


def _divergences(candidate: ClaimPaperCandidate, hit) -> list[CandidateMetadataDivergence]:
    """Fields where a matched candidate and an incoming record disagree.

    A value the record does not carry is never a divergence: an import that omits a
    journal is silent about it, not a claim that there is none. `current=None` marks a
    gap the record would fill rather than a contradiction.
    """
    out = []
    for field in REPAIRABLE_FIELDS:
        incoming = _as_text(getattr(hit, field, None))
        if incoming is None or not incoming.strip():
            continue
        current = _as_text(getattr(candidate, field, None))
        if field in ("doi", "pmid"):     # compare on the normalized form, as dedupe does
            norm = normalize_doi if field == "doi" else normalize_pmid
            if norm(current) == norm(incoming):
                continue
        elif (current or "").strip() == incoming.strip():
            continue
        out.append(CandidateMetadataDivergence(
            candidate_id=candidate.candidate_id, record_id=candidate.record_id,
            field=field, current=current, incoming=incoming))
    return out


class CandidateService:
    def __init__(self, store) -> None:
        self.store = store

    def _existing(self, claim_id: str) -> ClaimCandidates:
        if self.store.candidates_exist(claim_id):
            return self.store.load_candidates(claim_id)
        return ClaimCandidates(claim_id=claim_id)

    def link_from_intake(self, claim_id: str, batch_id: str,
                         record_ids: Optional[list[str]] = None) -> CandidateLinkReport:
        """Link a batch's intake hits to a claim as candidates.

        The report carries the candidates themselves, not just how many were added: a
        command that links objects should hand back those objects, so the caller can go
        straight on to rate them instead of re-listing the claim to find their ids. Matches
        are reported alongside new links, which makes the report idempotent — running this
        twice describes the same set both times rather than reducing to `linked: 0`.

        A match whose metadata contradicts the incoming record is reported as a divergence
        and left alone. Correcting it is `refresh_from_intake` — an explicit, audited act.
        """
        # claim must exist (raises StateError otherwise) -- never link to a phantom claim
        self.store.load_claim(claim_id)
        rec = self.store.load_intake(batch_id)

        cc = self._existing(claim_id)
        by_key = {_paper_key(c.pmid, c.doi, c.record_id): c for c in cc.candidates}
        want = set(record_ids) if record_ids else None

        linked = skipped = 0
        resolved: list[ClaimPaperCandidate] = []
        divergences: list[CandidateMetadataDivergence] = []
        for rank, hit in enumerate(rec.hits):
            if want is not None and hit.record_id not in want:
                continue
            key = _paper_key(hit.pmid, hit.doi, hit.record_id)
            already = by_key.get(key)
            if already is not None:
                # Already a candidate for this claim. Report WHICH one: the caller asked
                # about this source, and a bare count leaves them without the id they need
                # to rate it -- the reason a re-run used to look like it did nothing.
                # Report a contradiction too; a corrected import that lands here would
                # otherwise leave the stale record standing with nothing said about it.
                skipped += 1
                resolved.append(already)
                divergences.extend(_divergences(already, hit))
                continue
            cand = ClaimPaperCandidate(
                candidate_id=f"cand-{sha256_hex(claim_id + '|' + key)[:12]}",
                claim_id=claim_id, record_id=hit.record_id, intake_batch_id=batch_id,
                retrieval_query=rec.exact_query, retrieval_source=rec.provider,
                retrieval_rank=rank, why_found=hit.dedupe_status,
                already_in_zotero=(hit.dedupe_status == "already_in_library"),
                dedupe_status=hit.dedupe_status,
                pmid=hit.pmid, doi=hit.doi, title=hit.title, journal=hit.journal,
                year=hit.year, publication_date=hit.publication_date,
                abstract=getattr(hit, "abstract", None),
                created_at=utc_now_iso())
            by_key[key] = cand
            cc.candidates.append(cand)
            resolved.append(cand)
            linked += 1

        cc.updated_at = utc_now_iso()
        cc.provenance = Provenance(
            tool="claim_link_candidates", tool_version=__version__, ran_at=utc_now_iso(),
            config_hash=config_hash({"claim_id": claim_id, "batch_id": batch_id}),
            sources=[{"kind": "intake", "detail": batch_id}])
        self.store.save_candidates(cc)
        return CandidateLinkReport(
            claim_id=claim_id, intake_batch_id=batch_id, linked=linked,
            skipped_duplicates=skipped, total_candidates=len(cc.candidates),
            candidates=resolved, divergences=divergences, audit_event_id=cc.audit_event_id)

    def refresh_from_intake(self, claim_id: str, candidate_id: str,
                            batch_id: str) -> CandidateRepairReport:
        """Correct a candidate's descriptive metadata from a re-imported record.

        The repair dedupe leaves undone. Once an identifier is known, a re-import of a
        corrected record matches the candidate already on file and stops there, so the
        original's stale title stands however many times it is re-imported. This is the
        explicit way out — and it is explicit on purpose: a candidate's title is what a
        rater read, so refreshing it automatically would rewrite the record of what was
        judged, quietly, on the strength of an import.

        The correction is written as an audited `candidate.correct` event carrying every
        field's old and new value, so the previous text stays recoverable from the chain
        rather than being replaced without trace. If the pair already holds human support
        ratings, they were made against the old metadata: the count is reported and stamped
        into the audit payload. It does not block the repair — the record should be right —
        but it is never absorbed silently.

        Only descriptive fields move (``REPAIRABLE_FIELDS``). How the paper entered
        consideration — its record id, retrieval query, source, rank — is provenance, and a
        later import does not get to rewrite it.
        """
        self.store.load_claim(claim_id)
        rec = self.store.load_intake(batch_id)
        cc = self._existing(claim_id)
        cand = next((c for c in cc.candidates if c.candidate_id == candidate_id), None)
        if cand is None:
            raise StateError(f"candidate {candidate_id!r} is not linked to claim {claim_id!r}")

        key = _paper_key(cand.pmid, cand.doi, cand.record_id)
        hit = next((h for h in rec.hits
                    if _paper_key(h.pmid, h.doi, h.record_id) == key), None)
        if hit is None:
            # Never repair from a record that isn't the same paper: matching on identifier
            # is the only thing that makes this a correction rather than an overwrite.
            raise StateError(
                f"batch {batch_id!r} holds no record matching candidate {candidate_id!r} "
                f"({key}) — a correction must come from the same paper")

        corrected = _divergences(cand, hit)
        rated = _human_rated_count(self.store, claim_id, candidate_id)
        if not corrected:
            return CandidateRepairReport(
                claim_id=claim_id, candidate_id=candidate_id, intake_batch_id=batch_id,
                human_rated_before=rated, audit_event_id=cc.audit_event_id)

        for d in corrected:
            setattr(cand, d.field, getattr(hit, d.field))
        cc.updated_at = utc_now_iso()
        cc.provenance = Provenance(
            tool="candidate_refresh", tool_version=__version__, ran_at=utc_now_iso(),
            config_hash=config_hash({"claim_id": claim_id, "candidate_id": candidate_id,
                                     "batch_id": batch_id}),
            sources=[{"kind": "intake", "detail": batch_id}])
        self.store.correct_candidates(cc, {
            "claim_id": claim_id, "candidate_id": candidate_id, "intake_batch_id": batch_id,
            "human_rated_before": rated,
            "fields": [{"field": d.field, "from": d.current, "to": d.incoming}
                       for d in corrected]})
        return CandidateRepairReport(
            claim_id=claim_id, candidate_id=candidate_id, intake_batch_id=batch_id,
            corrected=corrected, human_rated_before=rated, audit_event_id=cc.audit_event_id)

    def list_for_claim(self, claim_id: str) -> ClaimCandidates:
        return self._existing(claim_id)
