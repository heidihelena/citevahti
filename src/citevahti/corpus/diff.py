"""CorpusDiffService: compare snapshots (or snapshot vs current) + staleness."""

from __future__ import annotations

import uuid
from typing import Optional

from .. import __version__
from ..intake.dedupe import normalize_doi, normalize_pmid
from ..schemas.common import Provenance
from ..schemas.corpus import AffectedRefs, CorpusDiffReport, StudyChange
from ..schemas.snapshot import SnapshotItem
from ..util import config_hash, utc_now_iso
from .snapshot import metadata_hash as _md  # noqa: F401  (kept for parity)
from .source import CorpusItem, CorpusSource, metadata_hash


def _to_snapshot_items(items: list[CorpusItem]) -> dict[str, SnapshotItem]:
    out: dict[str, SnapshotItem] = {}
    for it in items:
        out[it.citekey or it.zotero_key] = SnapshotItem(
            zotero_key=it.zotero_key, citekey=it.citekey, item_version=it.item_version,
            title=it.title, doi=it.doi, pmid=it.pmid, year=it.year,
            metadata_hash=metadata_hash(it), fulltext_hash=it.fulltext_hash,
            attachment_hashes=it.attachment_hashes, retraction_status=it.retraction_status)
    return out


def _index(items: dict[str, SnapshotItem]):
    by_zkey, by_doi, by_pmid = {}, {}, {}
    for it in items.values():
        by_zkey[it.zotero_key] = it
        nd = normalize_doi(it.doi)
        if nd:
            by_doi[nd] = it
        np = normalize_pmid(it.pmid)
        if np:
            by_pmid[np] = it
    return by_zkey, by_doi, by_pmid


def _match(to_item: SnapshotItem, idx) -> Optional[SnapshotItem]:
    by_zkey, by_doi, by_pmid = idx
    # identity continuity: stable item key, then DOI, then PMID (citekey may change)
    if to_item.zotero_key in by_zkey:
        return by_zkey[to_item.zotero_key]
    nd = normalize_doi(to_item.doi)
    if nd and nd in by_doi:
        return by_doi[nd]
    np = normalize_pmid(to_item.pmid)
    if np and np in by_pmid:
        return by_pmid[np]
    return None


def _change_types(a: SnapshotItem, b: SnapshotItem) -> list[str]:
    types: list[str] = []
    if a.metadata_hash != b.metadata_hash:
        types.append("metadata")
    if normalize_doi(a.doi) != normalize_doi(b.doi) or normalize_pmid(a.pmid) != normalize_pmid(b.pmid):
        types.append("doi_pmid")
    if (a.title or "") != (b.title or "") or a.year != b.year:
        types.append("title_year")
    if a.fulltext_hash and b.fulltext_hash and a.fulltext_hash != b.fulltext_hash:
        types.append("fulltext")
    if a.attachment_hashes and b.attachment_hashes and a.attachment_hashes != b.attachment_hashes:
        types.append("attachment")
    return types


class CorpusDiffService:
    def __init__(self, store, source: Optional[CorpusSource] = None) -> None:
        self.store = store
        self.source = source

    def diff(self, from_snapshot_id: str, to_snapshot_id: Optional[str] = None,
             compare_to_current: bool = False, mark_stale: bool = False,
             library="personal") -> CorpusDiffReport:
        prov = Provenance(tool="corpus_diff", tool_version=__version__, ran_at=utc_now_iso(),
                          config_hash=config_hash({"from": from_snapshot_id, "to": to_snapshot_id,
                                                   "current": compare_to_current}),
                          sources=[{"kind": "local_state", "detail": "snapshot comparison"}])
        from_snap = self.store.load_snapshot(from_snapshot_id)
        from_items = from_snap.items

        if compare_to_current:
            if self.source is None:
                return CorpusDiffReport(from_snapshot_id=from_snapshot_id, to_snapshot_id="current",
                                        status="degraded", error_code="no_corpus_source",
                                        remediation="No corpus source for current comparison.",
                                        provenance=prov)
            live = self.source.items(library)
            if live is None:
                return CorpusDiffReport(from_snapshot_id=from_snapshot_id, to_snapshot_id="current",
                                        status="degraded", error_code="zotero_unavailable",
                                        remediation="Zotero unavailable; cannot compare to current.",
                                        provenance=prov)
            to_items = _to_snapshot_items(live)
            to_id = "current"
        else:
            if to_snapshot_id is None:
                return CorpusDiffReport(from_snapshot_id=from_snapshot_id, to_snapshot_id="",
                                        status="degraded", error_code="no_to_snapshot",
                                        remediation="Provide a to_snapshot_id, or set "
                                                    "compare_to_current to diff against the live corpus.",
                                        provenance=prov)
            to_items = self.store.load_snapshot(to_snapshot_id).items
            to_id = to_snapshot_id

        report = CorpusDiffReport(from_snapshot_id=from_snapshot_id, to_snapshot_id=to_id,
                                  mark_stale=mark_stale, provenance=prov)
        from_idx = _index(from_items)
        matched_from: set = set()
        for to_item in to_items.values():
            m = _match(to_item, from_idx)
            if m is None:
                report.added.append(to_item.citekey or to_item.zotero_key)
                continue
            matched_from.add(m.zotero_key)
            ct = _change_types(m, to_item)
            if ct:
                report.changed.append(StudyChange(
                    key=to_item.citekey or to_item.zotero_key, zotero_key=to_item.zotero_key,
                    citekey=to_item.citekey, change_types=ct))
        for fi in from_items.values():
            if fi.zotero_key not in matched_from:
                report.removed.append(fi.citekey or fi.zotero_key)

        report.stale_candidates = [c.key for c in report.changed] + report.removed
        self._affected(report)
        if mark_stale and report.stale_candidates:
            self._mark_stale(report)
        return report

    def _affected(self, report: CorpusDiffReport) -> None:
        emap = self.store.load_evidence_map()
        atts, ratings, recs, outs = set(), set(), set(), set()
        for key in report.stale_candidates:
            entry = emap.reverse_index.get(key)
            if entry is None:
                continue
            atts.update(entry.attachment_ids)
            ratings.update(entry.rating_ids)
            recs.update(entry.recommendation_node_ids)
            outs.update(entry.outcome_node_ids)
        report.affected = AffectedRefs(attachments=sorted(atts), ratings=sorted(ratings),
                                       recommendation_nodes=sorted(recs), outcome_nodes=sorted(outs))

    def _mark_stale(self, report: CorpusDiffReport) -> None:
        from ..evidence import EvidenceMapService
        svc = EvidenceMapService(self.store)
        emap = svc.load()
        added: list[str] = []
        for key in report.stale_candidates:
            # only citekey-linked studies can be reverse-indexed / flagged
            if key not in emap.reverse_index:
                report.warnings.append(f"no reverse-index entry for {key}; not flagged")
                continue
            att_id = f"stale-{key}-{uuid.uuid4().hex[:8]}"
            svc.add_staleness_flag_attachment(
                emap, att_id, citekey=key, persist=False,
                reason=f"corpus_diff {report.from_snapshot_id}->{report.to_snapshot_id}")
            added.append(att_id)
        if added:
            svc.rebuild_reverse_index(emap)
            svc.save(emap)
            report.stale_flags_added = added
            report.audit_event_id = self.store.audit.entries()[-1].hash
