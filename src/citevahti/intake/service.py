"""IntakeService: literature_search (PubMed) + import_results (manual)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import __version__
from ..schemas.common import Provenance
from ..schemas.intake import IntakeHit, IntakeRecord
from ..util import config_hash, sha256_hex, utc_now_iso
from .dedupe import LibraryDedupeIndex, make_record_id, normalize_doi, normalize_pmid
from .manual import ManualParseError, parse_manual


class IntakeService:
    def __init__(self, store, provider=None, library_index: Optional[LibraryDedupeIndex] = None) -> None:
        self.store = store
        self.provider = provider
        self.library_index = library_index

    # ---- helpers ---------------------------------------------------------
    def _batch_id(self, provider: str, question_id: Optional[str], key: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        qid = question_id or sha256_hex(key or "")[:8]
        return f"{stamp}-{provider}-{qid}"

    def _prior_keys(self) -> tuple[set, set]:
        pmids: set = set()
        dois: set = set()
        for bid in self.store.list_intake():
            try:
                rec = self.store.load_intake(bid)
            except Exception:  # noqa: BLE001
                continue
            for h in rec.hits:
                if h.pmid:
                    pmids.add(normalize_pmid(h.pmid))
                if h.doi:
                    dois.add(normalize_doi(h.doi))
        return pmids, dois

    def _provenance(self, tool: str, payload: dict) -> Provenance:
        return Provenance(tool=tool, tool_version=__version__, ran_at=utc_now_iso(),
                          config_hash=config_hash(payload),
                          sources=[{"kind": "pubmed" if tool == "literature_search" else "local_state",
                                    "detail": "intake staging (pre-decision)"}])

    def _build_hits(self, raw: list[dict], include_abstracts: bool):
        prior_pmids, prior_dois = self._prior_keys()
        run_pmids: set = set()
        run_dois: set = set()
        hits: list[IntakeHit] = []
        dedupe_against = ["in_run", "prior_intake"]
        lib_used = False
        lib_status = "ok"

        for r in raw:
            np = normalize_pmid(r.get("pmid"))
            nd = normalize_doi(r.get("doi"))
            rid = make_record_id(np, nd, r.get("title", ""))
            if (np and np in run_pmids) or (nd and nd in run_dois):
                status = "duplicate_in_run"
            elif (np and np in prior_pmids) or (nd and nd in prior_dois):
                status = "already_in_prior_intake"
            else:
                status = "new"
                if self.library_index is not None:
                    lib_used = True
                    lib = self.library_index.contains(r.get("pmid"), r.get("doi"))
                    if lib is None:
                        lib_status = "degraded"   # Zotero unavailable -> cannot confirm
                    elif lib is True:
                        status = "already_in_library"
            if np:
                run_pmids.add(np)
            if nd:
                run_dois.add(nd)
            hits.append(IntakeHit(
                record_id=rid, pmid=r.get("pmid"), doi=r.get("doi"),
                title=r.get("title", "") or "", authors=list(r.get("authors") or []),
                journal=r.get("journal"), publication_date=r.get("publication_date"),
                year=r.get("year"),
                abstract=r.get("abstract") if include_abstracts else None,
                dedupe_status=status, decision=None))

        if lib_used:
            dedupe_against.append("zotero_library" if lib_status == "ok"
                                  else "zotero_library:degraded")
        digest = sha256_hex(",".join(sorted(run_pmids | {f"doi:{d}" for d in run_dois})))
        return hits, (lib_status if lib_used else None), dedupe_against, digest

    # ---- literature_search ----------------------------------------------
    def literature_search(self, query: str, question_id: Optional[str] = None,
                          max_results: int = 20, date_range: Optional[dict] = None,
                          include_abstracts: bool = False, library="personal") -> IntakeRecord:
        prov = self._provenance("literature_search", {"query": query, "max_results": max_results})
        res = self.provider.search(query, max_results, date_range, include_abstracts)
        # "warnings" is a SUCCESSFUL search with caveats (still stage); only the
        # hard statuses below are honest degradation.
        if res.status in ("missing_ncbi_email", "pubmed_unavailable", "pubmed_query_error"):
            # honest degradation: no fake hits, NOT persisted
            return IntakeRecord(
                batch_id=self._batch_id("pubmed", question_id, query), provider="pubmed",
                question_id=question_id, query=query, exact_query=query, run_at=utc_now_iso(),
                last_run_at=None, status="degraded", error_code=res.status,
                remediation=res.remediation, ncbi_email_present=res.email_present,
                ncbi_api_key_present=res.api_key_present, rate_tier=res.rate_tier,
                result_count=0, total_count=res.total_count,
                query_translation=res.query_translation,
                warnings=list(res.warnings) + list(res.errors), provenance=prov)

        raw = [vars(h) for h in res.hits]
        hits, lib_status, dedupe_against, digest = self._build_hits(raw, include_abstracts)
        record = IntakeRecord(
            batch_id=self._batch_id("pubmed", question_id, query), provider="pubmed",
            question_id=question_id, query=query, exact_query=query, run_at=utc_now_iso(),
            last_run_at=None, ncbi_email_present=res.email_present,
            ncbi_api_key_present=res.api_key_present, rate_tier=res.rate_tier,
            result_count=len(res.hits), total_count=res.total_count,
            query_translation=res.query_translation,
            dedupe_against=dedupe_against,
            library_dedupe_status=lib_status, seen_set_digest=digest, hits=hits,
            warnings=list(res.warnings) + list(res.errors),
            review_required=bool(res.warnings or res.errors),
            provenance=prov, status="ok")
        return self.store.save_intake(record)

    # ---- surveillance_refresh -------------------------------------------
    def _find_saved_query(self, query_id: str):
        candidates = []
        for bid in self.store.list_intake():
            try:
                rec = self.store.load_intake(bid)
            except Exception:  # noqa: BLE001
                continue
            if rec.provider != "pubmed" or not rec.exact_query:
                continue
            if query_id in (rec.question_id, rec.batch_id, rec.original_query_id):
                candidates.append(rec)
        if not candidates:
            return None
        # most recent run is the surveillance baseline
        return max(candidates, key=lambda r: (r.last_run_at or r.run_at or ""))

    @staticmethod
    def _pubmed_date(iso: Optional[str]) -> Optional[str]:
        if not iso:
            return None
        return iso[:10].replace("-", "/") if len(iso) >= 10 else None

    def _append_date(self, query: str, baseline_pubmed: Optional[str]) -> str:
        # mechanical append, NOT a semantic rewrite of the search strategy
        if not baseline_pubmed:
            return query
        return (f'({query}) AND ("{baseline_pubmed}"[Date - Publication] '
                f': "3000"[Date - Publication])')

    def surveillance_refresh(self, query_id: str, max_results: int = 20,
                             map_to: Optional[dict] = None, library="personal") -> IntakeRecord:
        prov = Provenance(tool="surveillance_refresh", tool_version=__version__,
                          ran_at=utc_now_iso(),
                          config_hash=config_hash({"query_id": query_id, "max_results": max_results}),
                          sources=[{"kind": "pubmed", "detail": "refresh from saved last-run date"}])
        saved = self._find_saved_query(query_id)
        if saved is None:
            return IntakeRecord(batch_id=self._batch_id("pubmed", query_id, query_id),
                                provider="pubmed", status="degraded", error_code="query_not_found",
                                remediation=f"No saved PubMed intake with query_id {query_id!r}.",
                                original_query_id=query_id, provenance=prov)

        baseline = self._pubmed_date(saved.last_run_at or saved.run_at)
        original = saved.exact_query
        sent = self._append_date(original, baseline)
        res = self.provider.search(sent, max_results, date_range=None, include_abstracts=False)
        common = dict(provider="pubmed", question_id=saved.question_id, query=original,
                      exact_query=original, exact_query_sent=sent, baseline_date=baseline,
                      original_query_id=query_id, run_at=utc_now_iso(),
                      last_run_at=saved.run_at, ncbi_email_present=res.email_present,
                      ncbi_api_key_present=res.api_key_present, rate_tier=res.rate_tier,
                      provenance=prov)
        if res.status != "ok":
            return IntakeRecord(batch_id=self._batch_id("pubmed", query_id, sent),
                                status="degraded", error_code=res.status,
                                remediation=res.remediation, result_count=0, **common)
        raw = [vars(h) for h in res.hits]
        hits, lib_status, dedupe_against, digest = self._build_hits(raw, include_abstracts=False)
        record = IntakeRecord(batch_id=self._batch_id("pubmed", query_id, sent), status="ok",
                              result_count=len(res.hits), dedupe_against=dedupe_against,
                              library_dedupe_status=lib_status, seen_set_digest=digest, hits=hits,
                              **common)
        return self.store.save_intake(record)

    # ---- import_results --------------------------------------------------
    def import_results(self, source: dict, fmt: str, question_id: Optional[str] = None,
                       source_label: Optional[str] = None, library="personal") -> IntakeRecord:
        text = source.get("text")
        if text is None and source.get("path"):
            text = Path(source["path"]).read_text(encoding="utf-8", errors="replace")
        prov = self._provenance("import_results", {"format": fmt, "label": source_label})
        if text is None:
            return IntakeRecord(batch_id=self._batch_id("manual", question_id, source_label or ""),
                                provider="manual", status="degraded", error_code="no_source",
                                remediation="Provide source.path or source.text.",
                                source_format=fmt, source_label=source_label,
                                imported_at=utc_now_iso(), provenance=prov)
        source_hash = sha256_hex(text)
        try:
            raw = parse_manual(text, fmt)
        except ManualParseError as exc:
            # fail cleanly: NOT persisted, no partial write
            return IntakeRecord(batch_id=self._batch_id("manual", question_id, source_hash),
                                provider="manual", status="degraded", error_code="parse_error",
                                remediation=str(exc), source_format=fmt, source_label=source_label,
                                source_hash=source_hash, imported_at=utc_now_iso(), provenance=prov)

        hits, lib_status, dedupe_against, digest = self._build_hits(raw, include_abstracts=True)
        record = IntakeRecord(
            batch_id=self._batch_id("manual", question_id, source_hash), provider="manual",
            question_id=question_id, source_label=source_label, source_format=fmt,
            source_hash=source_hash, imported_at=utc_now_iso(), last_run_at=None,
            dedupe_against=dedupe_against, library_dedupe_status=lib_status,
            seen_set_digest=digest, result_count=len(raw), hits=hits, provenance=prov, status="ok")
        return self.store.save_intake(record)
