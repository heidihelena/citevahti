"""Corpus source seam: read-only enumeration of library items for snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from ..schemas.snapshot import ProbeSummary
from ..util import canonical_json, sha256_hex


@dataclass
class CorpusItem:
    zotero_key: str
    citekey: Optional[str] = None
    item_version: Optional[int] = None
    title: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    year: Optional[int] = None
    fulltext_hash: Optional[str] = None
    attachment_hashes: Optional[list[str]] = None
    retraction_status: str = "unknown"


def metadata_hash(item: CorpusItem) -> str:
    return sha256_hex(canonical_json({
        "title": (item.title or "").strip().lower(),
        "doi": (item.doi or "").strip().lower(),
        "pmid": (item.pmid or "").strip(),
        "year": item.year,
    }))


@runtime_checkable
class CorpusSource(Protocol):
    def zotero_probe(self) -> ProbeSummary: ...
    def bbt_probe(self) -> ProbeSummary: ...
    def items(self, library="personal", include_fulltext_hashes: bool = False,
              include_retraction_status: bool = False) -> Optional[list[CorpusItem]]: ...


class StaticCorpusSource:
    """In-memory corpus source for tests/offline use."""

    def __init__(self, items: Optional[list[CorpusItem]] = None, zotero_available: bool = True,
                 bbt_available: bool = True, zotero_version: Optional[str] = "9.0.4",
                 bbt_version: Optional[str] = "9.0.27") -> None:
        self._items = items or []
        self.zotero_available = zotero_available
        self.bbt_available = bbt_available
        self._zver = zotero_version
        self._bver = bbt_version

    def zotero_probe(self) -> ProbeSummary:
        return ProbeSummary(available=self.zotero_available, version=self._zver,
                            version_status="parsed" if self._zver else None)

    def bbt_probe(self) -> ProbeSummary:
        return ProbeSummary(available=self.bbt_available, version=self._bver,
                            version_status="parsed" if self._bver else None)

    def items(self, library="personal", include_fulltext_hashes=False,
              include_retraction_status=False) -> Optional[list[CorpusItem]]:
        if not self.zotero_available:
            return None
        out = []
        for it in self._items:
            ck = it.citekey if self.bbt_available else None
            out.append(CorpusItem(
                zotero_key=it.zotero_key, citekey=ck, item_version=it.item_version,
                title=it.title, doi=it.doi, pmid=it.pmid, year=it.year,
                fulltext_hash=it.fulltext_hash if include_fulltext_hashes else None,
                attachment_hashes=it.attachment_hashes if include_fulltext_hashes else None,
                retraction_status=it.retraction_status))
        return out


class ZoteroCorpusSource:
    """Live read-only corpus source (Zotero local API + BBT citekeys)."""

    def __init__(self, zotero, bbt=None, capability=None, list_limit: int = 200) -> None:
        self.zotero = zotero
        self.bbt = bbt
        self.capability = capability
        self.list_limit = list_limit

    def zotero_probe(self) -> ProbeSummary:
        if self.capability is not None:
            r = self.capability.results.get("zotero_api")
            if r is not None:
                return ProbeSummary(available=r.available, version=r.version,
                                    version_status=r.version_status, detail=r.detail)
        return ProbeSummary(available=True)

    def bbt_probe(self) -> ProbeSummary:
        if self.capability is not None:
            r = self.capability.results.get("bbt_ready")
            if r is not None:
                return ProbeSummary(available=r.available, version=r.version,
                                    version_status=r.version_status, detail=r.detail)
        return ProbeSummary(available=self.bbt is not None)

    def _citekey(self, item_key: str) -> Optional[str]:
        if self.bbt is None:
            return None
        try:
            result = self.bbt.jsonrpc("item.citationkey", [[item_key]])
        except Exception:  # noqa: BLE001
            return None
        if isinstance(result, dict):
            val = result.get(item_key)
            return str(val) if val else None
        return None

    def items(self, library="personal", include_fulltext_hashes=False,
              include_retraction_status=False) -> Optional[list[CorpusItem]]:
        res = self.zotero.zot_search("", library=library, limit=self.list_limit)
        if not res.ok:
            return None
        out: list[CorpusItem] = []
        for it in res.data or []:
            key = it.get("key")
            if not key:
                continue
            ft = None
            if include_fulltext_hashes:
                fr = self.zotero.zot_fulltext(_ref(key, library))
                if fr.ok and fr.data and fr.data.get("content"):
                    ft = sha256_hex(fr.data["content"])
            out.append(CorpusItem(
                zotero_key=key, citekey=self._citekey(key),
                item_version=it.get("version"), title=it.get("title"),
                doi=it.get("DOI"), pmid=_extract_pmid(it),
                year=_year(it.get("date")), fulltext_hash=ft))
        return out


def _ref(item_key: str, library):
    from ..schemas.common import ItemRef
    return ItemRef(zotero_key=item_key, library=library)


def _extract_pmid(item: dict) -> Optional[str]:
    extra = item.get("extra") or ""
    import re
    m = re.search(r"PMID:\s*(\d+)", extra)
    return m.group(1) if m else None


def _year(date) -> Optional[int]:
    if not date:
        return None
    import re
    m = re.search(r"\d{4}", str(date))
    return int(m.group(0)) if m else None
