"""RetractionScanService: DOI/PMID retraction scan + optional staleness flags."""

from __future__ import annotations

import uuid
from typing import Optional

from .. import __version__
from ..intake.dedupe import normalize_doi, normalize_pmid
from ..schemas.common import Provenance
from ..schemas.results import AffectedRefs, RetractedItem, RetractionScanReport
from ..util import config_hash, utc_now_iso
from .provider import RetractionProvider, RetractionProviderUnavailable


class RetractionScanService:
    def __init__(self, store, provider: RetractionProvider) -> None:
        self.store = store
        self.provider = provider

    def _resolve_citekeys(self, citekeys: list[str]) -> dict[str, dict]:
        """Map citekeys -> {doi,pmid} using the most recent snapshot (no title match)."""
        out = {ck: {"doi": None, "pmid": None} for ck in citekeys}
        snaps = self.store.list_snapshots()
        if not snaps:
            return out
        snap = self.store.load_snapshot(snaps[-1])
        for ck in citekeys:
            it = snap.items.get(ck)
            if it is not None:
                out[ck] = {"doi": it.doi, "pmid": it.pmid}
        return out

    def scan(self, selection: Optional[dict] = None, library="personal",
             mark_stale: bool = False) -> RetractionScanReport:
        selection = selection or {}
        prov = Provenance(tool="retraction_scan", tool_version=__version__, ran_at=utc_now_iso(),
                          config_hash=config_hash({"selection": selection}),
                          sources=[{"kind": "retraction_provider", "detail": "DOI/PMID lookup"}])
        report = RetractionScanReport(mark_stale=mark_stale, provenance=prov)

        candidates: list[dict] = []
        for doi in selection.get("dois", []) or []:
            candidates.append({"citekey": None, "doi": doi, "pmid": None})
        for pmid in selection.get("pmids", []) or []:
            candidates.append({"citekey": None, "doi": None, "pmid": pmid})
        resolved = self._resolve_citekeys(selection.get("citekeys", []) or [])
        for ck, ids in resolved.items():
            candidates.append({"citekey": ck, "doi": ids["doi"], "pmid": ids["pmid"]})

        for cand in candidates:
            if not cand["doi"] and not cand["pmid"]:
                report.warnings.append(
                    f"no DOI/PMID for {cand['citekey'] or '?'}; skipped (no title matching)")
                continue
            report.scanned_count += 1
            try:
                res = self.provider.lookup(doi=cand["doi"], pmid=cand["pmid"])
            except RetractionProviderUnavailable as exc:
                report.status = "degraded"
                report.error_code = "provider_unavailable"
                report.remediation = f"Retraction provider offline: {exc}. No retractions inferred."
                report.retracted = []   # never fabricate
                return report
            if res is not None and res.retracted:
                report.retracted.append(RetractedItem(
                    citekey=cand["citekey"], doi=cand["doi"], pmid=cand["pmid"],
                    status=res.status, source=res.source, notice_url=res.notice_url))

        self._affected(report)
        if mark_stale and report.retracted:
            self._mark(report)
        return report

    def _affected(self, report: RetractionScanReport) -> None:
        emap = self.store.load_evidence_map()
        atts, ratings, recs, outs = set(), set(), set(), set()
        for r in report.retracted:
            if not r.citekey:
                continue
            entry = emap.reverse_index.get(r.citekey)
            if entry is None:
                continue
            atts.update(entry.attachment_ids)
            ratings.update(entry.rating_ids)
            recs.update(entry.recommendation_node_ids)
            outs.update(entry.outcome_node_ids)
        report.affected = AffectedRefs(attachments=sorted(atts), ratings=sorted(ratings),
                                       recommendation_nodes=sorted(recs), outcome_nodes=sorted(outs))

    def _mark(self, report: RetractionScanReport) -> None:
        from ..evidence import EvidenceMapService
        svc = EvidenceMapService(self.store)
        emap = svc.load()
        retraction_ids, stale_ids = [], []
        for r in report.retracted:
            if not r.citekey:
                report.warnings.append(f"retracted item {r.doi or r.pmid} has no citekey; not flagged")
                continue
            rid = f"retraction-{r.citekey}-{uuid.uuid4().hex[:8]}"
            svc.add_retraction_flag_attachment(emap, rid, citekey=r.citekey,
                                               notice=r.notice_url, persist=False)
            retraction_ids.append(rid)
            # flag affected assessments (via reverse index) as stale
            if r.citekey in emap.reverse_index:
                sid = f"stale-retraction-{r.citekey}-{uuid.uuid4().hex[:8]}"
                svc.add_staleness_flag_attachment(emap, sid, citekey=r.citekey, persist=False,
                                                  reason=f"retraction:{r.doi or r.pmid}")
                stale_ids.append(sid)
        if retraction_ids or stale_ids:
            svc.rebuild_reverse_index(emap)
            svc.save(emap)
            report.retraction_flags_added = retraction_ids
            report.staleness_flags_added = stale_ids
            report.audit_event_id = self.store.audit.entries()[-1].hash
