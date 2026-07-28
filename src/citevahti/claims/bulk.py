"""Bulk claim import: one JSONL file -> claims, candidates, and open rating slots.

Loading a corpus by hand meant ~90 lines of scripting across `import-results`, `claim-add`,
`claim-link-candidates` and `claim-support-start`, plumbing ids between every step. Agents
are how most corpora will be loaded, and every id hop was somewhere to drop one.

**Resumable, not atomic.** There is no general ledger transaction in CiteVahti —
`ZoteroTransaction` / `txn-undo` cover Zotero writes only — so this does not claim
all-or-nothing. Instead every step is idempotent, which for an interrupted load is the more
useful property: re-run the same file and it converges rather than duplicating. A claim
matches on normalized claim text + location instead of being created twice; candidates
dedupe by identifier as always; opening a rating returns the pair's existing open slot. What
a re-run *does* add is a fresh intake batch — that is honest, because re-importing really is
a new import event, and it is the record of when these records were staged.

Rows are validated before anything is written, so a typo on line 40 cannot leave 39 rows
half-loaded. `dry_run=True` reports the same plan and writes nothing at all.

The import decides nothing. It opens rating slots; every judgement is still made by a human
afterwards, and no AI runs here.
"""

from __future__ import annotations

from typing import Optional

from ..schemas.claim import CLAIM_TYPES
from ..schemas.claims_import import ClaimsImportReport, ImportedClaim, ImportedSource
from ..util import claim_text_hash
from ..intake.dedupe import make_record_id, normalize_doi, normalize_pmid
from .candidates import CandidateService
from .service import ClaimService
from .support import ClaimSupportEngine

# Row fields a source may carry. Anything else is a typo worth failing on rather than
# silently dropping -- a misspelled "doi" would otherwise import as a title-only source.
SOURCE_FIELDS = ("doi", "pmid", "title", "journal", "year", "publication_date", "abstract",
                 "authors")
ROW_FIELDS = ("claim_text", "location", "claim_type", "sources", "manuscript_id")


class ClaimsImportError(Exception):
    """A row the caller must fix. Raised before any write."""

    code = "claims_import_error"


def _identifier(pmid: Optional[str], doi: Optional[str]) -> Optional[str]:
    np, nd = normalize_pmid(pmid), normalize_doi(doi)
    if np:
        return f"pmid:{np}"
    if nd:
        return f"doi:{nd}"
    return None


def validate_rows(rows: list[dict]) -> list[str]:
    """Check every row up front and return the non-fatal warnings.

    Fatal problems raise, naming the 1-based row, because a bulk load that fails halfway
    is worse than one that does not start: the caller cannot tell what landed.
    """
    warnings: list[str] = []
    if not rows:
        raise ClaimsImportError("no rows to import")
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ClaimsImportError(f"row {i}: expected a JSON object, got {type(row).__name__}")
        unknown = set(row) - set(ROW_FIELDS)
        if unknown:
            raise ClaimsImportError(f"row {i}: unknown field(s) {sorted(unknown)}; "
                                    f"expected {list(ROW_FIELDS)}")
        text = (row.get("claim_text") or "").strip()
        if not text:
            raise ClaimsImportError(f"row {i}: claim_text is required and cannot be blank")
        ctype = row.get("claim_type") or "other"
        if ctype not in CLAIM_TYPES:
            raise ClaimsImportError(f"row {i}: claim_type {ctype!r} is not one of "
                                    f"{list(CLAIM_TYPES)}")
        sources = row.get("sources") or []
        if not isinstance(sources, list):
            raise ClaimsImportError(f"row {i}: sources must be a list")
        if not sources:
            warnings.append(f"row {i}: no sources — the claim is created with nothing to rate")
        for j, src in enumerate(sources, start=1):
            if not isinstance(src, dict):
                raise ClaimsImportError(f"row {i} source {j}: expected a JSON object")
            unknown = set(src) - set(SOURCE_FIELDS)
            if unknown:
                raise ClaimsImportError(f"row {i} source {j}: unknown field(s) {sorted(unknown)}; "
                                        f"expected {list(SOURCE_FIELDS)}")
            if not _identifier(src.get("pmid"), src.get("doi")):
                if not (src.get("title") or "").strip():
                    raise ClaimsImportError(
                        f"row {i} source {j}: needs a doi, a pmid, or at least a title")
                # Invariant 11: title is never dedupe truth. Such a source cannot be matched
                # to the same paper cited elsewhere, so say so rather than imply it was.
                warnings.append(
                    f"row {i} source {j}: title only, no doi/pmid — it cannot be deduped "
                    f"against the same paper cited elsewhere")
    return warnings


class ClaimsImportService:
    def __init__(self, store) -> None:
        self.store = store

    def _claim_index(self) -> dict:
        """Existing claims by (normalized claim text, location) — the re-run match key.

        Text alone is not enough: the same sentence asserted in two places is two claims
        with two sets of sources. `claim_text_hash` is the shared cross-tool normalization,
        so this matches the way every other surface compares claim text.
        """
        idx: dict[tuple[str, str], str] = {}
        for cid in self.store.list_claims():
            claim = self.store.load_claim(cid)
            idx.setdefault(
                (claim_text_hash(claim.claim_text), claim.manuscript_location or ""), cid)
        return idx

    def import_rows(self, rows: list[dict], *, question_id: Optional[str] = None,
                    source_label: Optional[str] = None,
                    dry_run: bool = False) -> ClaimsImportReport:
        warnings = validate_rows(rows)      # raises before anything is written
        report = ClaimsImportReport(dry_run=dry_run, rows=len(rows), warnings=warnings)
        index = self._claim_index()

        # Every source across the file, deduped, staged as ONE intake batch: the papers
        # entered consideration together, in one import event, and the batch is that record.
        records, keys = [], []
        seen: dict[str, str] = {}
        for row in rows:
            row_keys = []
            for src in row.get("sources") or []:
                rid = make_record_id(normalize_pmid(src.get("pmid")),
                                     normalize_doi(src.get("doi")), src.get("title") or "")
                if rid not in seen:
                    seen[rid] = rid
                    records.append({k: src.get(k) for k in SOURCE_FIELDS})
                row_keys.append(rid)
            keys.append(row_keys)
        report.title_only_sources = sum(1 for r in records
                                        if not _identifier(r.get("pmid"), r.get("doi")))

        batch_id = None
        if not dry_run and records:
            from ..intake import IntakeService
            batch = IntakeService(self.store).import_records(
                records, question_id=question_id, source_label=source_label)
            batch_id = batch.batch_id
        report.intake_batch_id = batch_id

        candidates = CandidateService(self.store)
        claims = ClaimService(self.store)
        engine = ClaimSupportEngine(self.store)

        for i, (row, row_keys) in enumerate(zip(rows, keys), start=1):
            text = row["claim_text"].strip()
            location = row.get("location")
            key = (claim_text_hash(text), location or "")
            existing = index.get(key)

            entry = ImportedClaim(row=i, claim_text=text,
                                  status="matched" if existing else
                                  ("would_create" if dry_run else "created"))
            claim_id = existing or ""
            if existing:
                report.claims_matched += 1
                entry.claim_id = existing
            elif dry_run:
                report.claims_created += 1
            else:
                claim = claims.add_claim(
                    text, row.get("claim_type") or "other", manuscript_location=location,
                    manuscript_id=row.get("manuscript_id"),
                    # the rows were written by a person or an agent transcribing a
                    # manuscript, not extracted by a model inside CiteVahti
                    extracted_by="imported")
                claim_id = claim.claim_id
                entry.claim_id = claim_id
                index[key] = claim_id
                report.claims_created += 1

            if dry_run:
                for rid in row_keys:
                    entry.sources.append(ImportedSource(
                        record_id=rid, identifier=rid if rid.startswith(("doi:", "pmid:")) else None,
                        status="would_link"))
                report.claims.append(entry)
                continue

            # What the claim held BEFORE this link tells us which candidates this run added.
            # The batch id cannot: it carries a second-resolution timestamp, so a re-run
            # inside the same second reuses it and every candidate would read as fresh.
            before = {c.candidate_id for c in candidates.list_for_claim(claim_id).candidates}
            linked = (candidates.link_from_intake(claim_id, batch_id, record_ids=row_keys)
                      if row_keys and batch_id else None)
            for cand in (linked.candidates if linked else []):
                fresh = cand.candidate_id not in before
                # Opening a rating is idempotent, so a resumed run reuses the pair's open
                # slot instead of forking it. It records no judgement.
                rating = engine.support_start(claim_id, cand.candidate_id)
                entry.sources.append(ImportedSource(
                    record_id=cand.record_id or "", identifier=_identifier(cand.pmid, cand.doi),
                    title=cand.title, candidate_id=cand.candidate_id, rating_id=rating.rating_id,
                    status="linked" if fresh else "already_linked"))
                if fresh:
                    report.candidates_linked += 1
                else:
                    report.candidates_already_linked += 1
                report.ratings_opened += 1
            if linked and linked.divergences:
                for d in linked.divergences:
                    entry.warnings.append(
                        f"{d.candidate_id} {d.field} differs from the record already on file "
                        f"({d.current!r} vs {d.incoming!r}) — nothing changed; "
                        f"see `citevahti candidate-refresh`")
            report.claims.append(entry)

        return report
