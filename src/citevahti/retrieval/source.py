"""Text sources: the read-only seam the retrieval service depends on.

``ZoteroApiTextSource`` is the live implementation (Zotero local API + Better
BibTeX for citekey resolution). ``StaticTextSource`` is a deterministic double so
extraction/claim-check unit tests run fully offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from ..schemas.common import ItemRef


@dataclass
class FullTextDoc:
    text: str
    attachment_key: Optional[str] = None
    indexed_pages: Optional[int] = None


@dataclass
class AnnotationDoc:
    key: str
    text: str = ""
    comment: Optional[str] = None
    page_label: Optional[str] = None
    page_index: Optional[int] = None
    attachment_key: Optional[str] = None


@runtime_checkable
class TextSource(Protocol):
    def resolve_citekey(self, citekey: str, library="personal") -> Optional[ItemRef]: ...

    def fulltext(self, ref: ItemRef, attachment_key: Optional[str] = None) -> Optional[FullTextDoc]: ...

    def annotations(self, ref: ItemRef, attachment_key: Optional[str] = None) -> list[AnnotationDoc]: ...


class StaticTextSource:
    """In-memory text source keyed by citekey or zotero item key."""

    def __init__(self, items: Optional[dict[str, ItemRef]] = None,
                 fulltext: Optional[dict[str, FullTextDoc]] = None,
                 annotations: Optional[dict[str, list[AnnotationDoc]]] = None) -> None:
        self.items = items or {}
        self._fulltext = fulltext or {}
        self._annotations = annotations or {}

    def _keys(self, ref: ItemRef) -> list[str]:
        return [k for k in (ref.zotero_key, ref.citekey) if k]

    def resolve_citekey(self, citekey: str, library="personal") -> Optional[ItemRef]:
        return self.items.get(citekey)

    def fulltext(self, ref: ItemRef, attachment_key: Optional[str] = None) -> Optional[FullTextDoc]:
        for k in self._keys(ref):
            if k in self._fulltext:
                return self._fulltext[k]
        return None

    def annotations(self, ref: ItemRef, attachment_key: Optional[str] = None) -> list[AnnotationDoc]:
        for k in self._keys(ref):
            if k in self._annotations:
                return self._annotations[k]
        return []


def _extract_item_key(item: dict) -> Optional[str]:
    for f in ("itemKey", "key", "zoteroKey", "itemID"):
        if item.get(f):
            return str(item[f])
    # Better BibTeX `item.search` returns CSL-JSON, where the item identity is a
    # URI in `id`, e.g. "http://zotero.org/users/424242/items/5H47Z9P9".
    cid = item.get("id")
    if isinstance(cid, str):
        m = re.search(r"/items/([A-Z0-9]+)", cid)
        if m:
            return m.group(1)
    return None


class ZoteroApiTextSource:
    """Live read-only source: Zotero local API + Better BibTeX resolution."""

    def __init__(self, zotero, bbt) -> None:
        self.zotero = zotero  # ZoteroService
        self.bbt = bbt        # BbtClient

    def resolve_citekey(self, citekey: str, library="personal") -> Optional[ItemRef]:
        from ..bbt.client import BbtUnavailable, _extract_citekey
        try:
            result = self.bbt.jsonrpc("item.search", [citekey])
        except BbtUnavailable:
            return None
        items = result if isinstance(result, list) else []
        for it in items:
            if isinstance(it, dict) and _extract_citekey(it) == citekey:
                key = _extract_item_key(it)
                if key:
                    return ItemRef(zotero_key=key, library=library, citekey=citekey)
        return None

    def fulltext(self, ref: ItemRef, attachment_key: Optional[str] = None) -> Optional[FullTextDoc]:
        res = self.zotero.zot_fulltext(ref, attachment_key)
        if not res.ok or not res.data or not res.data.get("content"):
            return None
        d = res.data
        return FullTextDoc(text=d["content"], attachment_key=d.get("attachment_key"),
                           indexed_pages=d.get("indexed_pages"))

    def annotations(self, ref: ItemRef, attachment_key: Optional[str] = None) -> list[AnnotationDoc]:
        res = self.zotero.zot_annotations(ref, attachment_key)
        if not res.ok or not res.data:
            return []
        out: list[AnnotationDoc] = []
        for a in res.data:
            out.append(AnnotationDoc(
                key=a.get("key", ""), text=a.get("text", "") or "",
                comment=a.get("comment"), page_label=a.get("page_label"),
                page_index=a.get("page_index"), attachment_key=a.get("attachment_key")))
        return out
