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
from ..schemas.candidate import CandidateLinkReport, ClaimCandidates, ClaimPaperCandidate
from ..schemas.common import Provenance
from ..util import config_hash, sha256_hex, utc_now_iso


def _paper_key(pmid: Optional[str], doi: Optional[str], record_id: Optional[str]) -> str:
    np, nd = normalize_pmid(pmid), normalize_doi(doi)
    if np:
        return f"pmid:{np}"
    if nd:
        return f"doi:{nd}"
    return f"rec:{record_id or ''}"


class CandidateService:
    def __init__(self, store) -> None:
        self.store = store

    def _existing(self, claim_id: str) -> ClaimCandidates:
        if self.store.candidates_exist(claim_id):
            return self.store.load_candidates(claim_id)
        return ClaimCandidates(claim_id=claim_id)

    def link_from_intake(self, claim_id: str, batch_id: str,
                         record_ids: Optional[list[str]] = None) -> CandidateLinkReport:
        # claim must exist (raises StateError otherwise) -- never link to a phantom claim
        self.store.load_claim(claim_id)
        rec = self.store.load_intake(batch_id)

        cc = self._existing(claim_id)
        seen = {_paper_key(c.pmid, c.doi, c.record_id) for c in cc.candidates}
        want = set(record_ids) if record_ids else None

        linked = skipped = 0
        for rank, hit in enumerate(rec.hits):
            if want is not None and hit.record_id not in want:
                continue
            key = _paper_key(hit.pmid, hit.doi, hit.record_id)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            cc.candidates.append(ClaimPaperCandidate(
                candidate_id=f"cand-{sha256_hex(claim_id + '|' + key)[:12]}",
                claim_id=claim_id, record_id=hit.record_id, intake_batch_id=batch_id,
                retrieval_query=rec.exact_query, retrieval_source=rec.provider,
                retrieval_rank=rank, why_found=hit.dedupe_status,
                already_in_zotero=(hit.dedupe_status == "already_in_library"),
                dedupe_status=hit.dedupe_status,
                pmid=hit.pmid, doi=hit.doi, title=hit.title, journal=hit.journal,
                year=hit.year, publication_date=hit.publication_date,
                abstract=getattr(hit, "abstract", None),
                created_at=utc_now_iso()))
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
            audit_event_id=cc.audit_event_id)

    def list_for_claim(self, claim_id: str) -> ClaimCandidates:
        return self._existing(claim_id)
