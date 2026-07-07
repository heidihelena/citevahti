"""Read-only Zotero / citation surface (ADR-0010 PR 1a — first tools/ split group).

Thin façade over the read-only Zotero local API and Better BibTeX. All reads honor the
library selector; ``cite`` never invents keys and fails on unresolved keys; every function
degrades honestly when its backend is absent. Nothing here mutates a library, the ledger,
or the filesystem — this is the safest group to move first (ADR-0010 §3, read-only first).

Re-exported unchanged from ``citevahti.tools`` so ``from citevahti.tools import zot_search``
still works (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ..cite import CiteService, CiteTarget
from ..probe.client import HttpxClient
from ..probe.probe import CapabilityReport
from ..schemas.common import ItemRef, LibrarySelector, ToolResult
from ..schemas.config import Endpoints
from ..zotero import ZoteroService


def _zotero(endpoints: Optional[Endpoints], capability: Optional[CapabilityReport]) -> ZoteroService:
    return ZoteroService(HttpxClient(), endpoints, capability)


def _cite(endpoints: Optional[Endpoints], capability: Optional[CapabilityReport]) -> CiteService:
    return CiteService(HttpxClient(), endpoints, capability)


# ---- step 2: read/discover (zot_*) + cite -------------------------------
def zot_search(query: str, library: LibrarySelector = "personal", limit: Optional[int] = None,
               *, endpoints: Optional[Endpoints] = None,
               capability: Optional[CapabilityReport] = None) -> ToolResult:
    return _zotero(endpoints, capability).zot_search(query, library, limit)


def zot_item(ref: ItemRef, *, endpoints: Optional[Endpoints] = None,
             capability: Optional[CapabilityReport] = None) -> ToolResult:
    return _zotero(endpoints, capability).zot_item(ref)


def zot_collections(library: LibrarySelector = "personal", *,
                    endpoints: Optional[Endpoints] = None,
                    capability: Optional[CapabilityReport] = None) -> ToolResult:
    return _zotero(endpoints, capability).zot_collections(library)


def zot_attachments(ref: ItemRef, *, endpoints: Optional[Endpoints] = None,
                    capability: Optional[CapabilityReport] = None) -> ToolResult:
    return _zotero(endpoints, capability).zot_attachments(ref)


def cite(target: CiteTarget, format: str = "pandoc", *,
         endpoints: Optional[Endpoints] = None,
         capability: Optional[CapabilityReport] = None) -> ToolResult:
    return _cite(endpoints, capability).cite(target, format)


def zotero_locate(*, doi: Optional[str] = None, title: Optional[str] = None,
                  pmid: Optional[str] = None, root: Optional[str] = None,
                  endpoints: Optional[Endpoints] = None, zotero=None) -> dict:
    """Find a library item matching a candidate, so the panel can deep-link to its
    PDF in Zotero (``zotero://open-pdf/...``). Matches by DOI when available."""
    z = zotero or ZoteroService(HttpxClient(), endpoints)
    query = doi or title or pmid
    if not query:
        return {"found": False}
    res = z.zot_search(str(query), limit=8)
    if not getattr(res, "ok", False):
        return {"found": False, "error": getattr(res, "error_code", None)}
    items = res.data or []
    match = None
    if doi:
        match = next((it for it in items if (it.get("DOI") or "").lower() == str(doi).lower()), None)
    if match is None and items:
        match = items[0]
    if match is None:
        return {"found": False}
    return {"found": True, "key": match.get("key"), "library": "personal"}


def zotero_evidence(*, doi: Optional[str] = None, title: Optional[str] = None,
                    pmid: Optional[str] = None, max_chars: int = 1500,
                    root: Optional[str] = None, endpoints: Optional[Endpoints] = None,
                    zotero=None) -> dict:
    """The paper's own highlights (PDF annotations) + an indexed full-text snippet
    from Zotero — content to read while rating. This is the paper's text, not an AI
    assessment, so it is blinding-safe (like the stored abstract)."""
    z = zotero or ZoteroService(HttpxClient(), endpoints)
    query = doi or title or pmid
    if not query:
        return {"found": False}
    res = z.zot_search(str(query), limit=8)
    if not getattr(res, "ok", False):
        return {"found": False, "error": getattr(res, "error_code", None)}
    items = res.data or []
    match = None
    if doi:
        match = next((it for it in items if (it.get("DOI") or "").lower() == str(doi).lower()), None)
    if match is None and items:
        match = items[0]
    if match is None:
        return {"found": False}
    ref = ItemRef(zotero_key=match.get("key"), library="personal")
    ann = z.zot_annotations(ref)
    annotations = ([{"text": a.get("text"), "comment": a.get("comment"), "page": a.get("page_label")}
                    for a in (ann.data or [])] if getattr(ann, "ok", False) else [])
    ft = z.zot_fulltext(ref)
    fulltext = ((ft.data or {}).get("content", "")[:max_chars]) if getattr(ft, "ok", False) else ""
    return {"found": True, "item_key": match.get("key"),
            "annotations": annotations, "fulltext": fulltext}


def pandoc_status():
    """Whether Pandoc is available WITHOUT triggering a download (on PATH or a copy
    fetched earlier). Lets the panel warn before the one-time first-run fetch."""
    from ..report.citation_export import _resolve_pandoc
    path, err = _resolve_pandoc(allow_download=False)
    return {"available": err is None, "path": path}
