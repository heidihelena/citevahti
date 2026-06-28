"""Deduplication keys + the read-only Zotero library dedupe seam.

DOI matching is normalized + case-insensitive; PMID matching is exact after
whitespace stripping. Title is never dedupe truth -- only a suspected-duplicate
warning at most.
"""

from __future__ import annotations

import re
from typing import Optional, Protocol, runtime_checkable

from ..util import sha256_hex

_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    d = _DOI_PREFIX.sub("", doi.strip()).strip().lower()
    return d or None


def normalize_pmid(pmid: Optional[str]) -> Optional[str]:
    if not pmid:
        return None
    p = re.sub(r"\s+", "", str(pmid))
    return p or None


def make_record_id(pmid: Optional[str], doi: Optional[str], title: str) -> str:
    if pmid:
        return f"pmid:{pmid}"
    if doi:
        return f"doi:{doi}"
    return f"title:{sha256_hex((title or '').strip().lower())[:12]}"


@runtime_checkable
class LibraryDedupeIndex(Protocol):
    # contains() returns True/False, or None when the library is unavailable.
    def contains(self, pmid: Optional[str], doi: Optional[str]) -> Optional[bool]: ...


class StaticLibraryIndex:
    """In-memory library index for tests/offline use."""

    def __init__(self, pmids=None, dois=None, available: bool = True) -> None:
        self.pmids = {normalize_pmid(p) for p in (pmids or [])}
        self.dois = {normalize_doi(d) for d in (dois or [])}
        self.available = available

    def contains(self, pmid: Optional[str], doi: Optional[str]) -> Optional[bool]:
        if not self.available:
            return None
        np, nd = normalize_pmid(pmid), normalize_doi(doi)
        if np and np in self.pmids:
            return True
        if nd and nd in self.dois:
            return True
        return False


class ZoteroLibraryIndex:
    """Live read-only library index backed by zot_search.

    Returns None (unavailable) once a Zotero read degrades, so the caller can
    mark library dedupe degraded rather than fabricate a status.
    """

    def __init__(self, zotero, library="personal") -> None:
        self.zotero = zotero
        self.library = library
        self.available = True

    def _items(self, query: str) -> Optional[list[dict]]:
        res = self.zotero.zot_search(query, library=self.library)
        if not res.ok:
            self.available = False
            return None
        return res.data or []

    def contains(self, pmid: Optional[str], doi: Optional[str]) -> Optional[bool]:
        if not self.available:
            return None
        nd = normalize_doi(doi)
        if nd:
            # Search with the NORMALIZED doi (matching the comparison below and the
            # PMID branch). Searching the raw form — e.g. "https://doi.org/10.1/ABC"
            # — can miss a library item stored canonically as "10.1/abc".
            items = self._items(nd)
            if items is None:
                return None
            for it in items:
                if normalize_doi(it.get("DOI")) == nd:
                    return True
        np = normalize_pmid(pmid)
        if np:
            items = self._items(np)
            if items is None:
                return None
            for it in items:
                extra = (it.get("extra") or "") + " " + str(it.get("PMID") or "")
                if re.search(rf"\bPMID:?\s*{re.escape(np)}\b", extra) or it.get("PMID") == np:
                    return True
        return False
