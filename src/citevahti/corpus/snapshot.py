"""SnapshotService: hashed read-only capture of corpus + evidence-map state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .. import __version__
from ..schemas.common import Provenance
from ..schemas.snapshot import SnapshotItem, SnapshotRecord
from ..util import canonical_json, config_hash, sha256_hex, utc_now_iso
from .source import CorpusSource, metadata_hash


def _evidence_hashes(emap) -> tuple[str, str]:
    blob = [n.model_dump() for n in emap.nodes]
    blob += [l.model_dump(by_alias=True) for l in emap.links]
    blob += [a.model_dump() for a in emap.attachments]
    em_hash = sha256_hex(canonical_json(blob))
    ri_hash = sha256_hex(canonical_json({k: v.model_dump() for k, v in emap.reverse_index.items()}))
    return em_hash, ri_hash


class SnapshotService:
    def __init__(self, store, source: CorpusSource) -> None:
        self.store = store
        self.source = source

    def _id(self, label: Optional[str]) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{sha256_hex((label or '') + stamp)[:8]}"

    def snapshot(self, label: Optional[str] = None, library="personal",
                 include_fulltext_hashes: bool = False,
                 include_retraction_status: bool = False) -> SnapshotRecord:
        zp = self.source.zotero_probe()
        bp = self.source.bbt_probe()
        prov = Provenance(tool="snapshot", tool_version=__version__, ran_at=utc_now_iso(),
                          config_hash=config_hash({"library": str(library),
                                                   "fulltext": include_fulltext_hashes}),
                          sources=[{"kind": "zotero_api", "detail": "read-only corpus capture"}])
        items = self.source.items(library, include_fulltext_hashes, include_retraction_status)
        if items is None:
            # Zotero unavailable -> do NOT write a fake snapshot
            return SnapshotRecord(snapshot_id=self._id(label), label=label, created_at=utc_now_iso(),
                                  library=str(library), zotero_probe=zp, bbt_probe=bp,
                                  status="degraded", error_code="zotero_unavailable",
                                  remediation="Zotero local API unavailable; no snapshot written.",
                                  provenance=prov)

        snap_items: dict[str, SnapshotItem] = {}
        for it in items:
            si = SnapshotItem(
                zotero_key=it.zotero_key, citekey=it.citekey, item_version=it.item_version,
                title=it.title, doi=it.doi, pmid=it.pmid, year=it.year,
                metadata_hash=metadata_hash(it), fulltext_hash=it.fulltext_hash,
                attachment_hashes=it.attachment_hashes, retraction_status=it.retraction_status)
            snap_items[it.citekey or it.zotero_key] = si  # citekey when available, else item key

        emap = self.store.load_evidence_map()
        em_hash, ri_hash = _evidence_hashes(emap)
        record = SnapshotRecord(
            snapshot_id=self._id(label), label=label, created_at=utc_now_iso(),
            library=str(library), zotero_probe=zp, bbt_probe=bp,
            citekey_coverage="ok" if bp.available else "degraded",
            include_fulltext_hashes=include_fulltext_hashes, items=snap_items,
            evidence_map_hash=em_hash, reverse_index_hash=ri_hash, provenance=prov, status="ok")
        if not bp.available:
            record.warnings.append("Better BibTeX unavailable; citekey coverage degraded")
        return self.store.save_snapshot(record)
