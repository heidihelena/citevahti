"""Read/discover tools backed by the Zotero local API (read-only / GET-only)."""

from __future__ import annotations

from typing import Any, Optional

from .. import __version__
from ..probe.client import HttpClient, ProbeTransportError
from ..probe.probe import CapabilityReport
from ..schemas.common import ItemRef, LibrarySelector, Provenance, ToolResult
from ..schemas.config import Endpoints
from ..util import config_hash, utc_now_iso
from .library import LibrarySelectorError, base_path, bases_for, coerce_library

ZOTERO_UNREACHABLE_REMEDIATION = (
    "Zotero local API is unreachable. Start Zotero 9.x and enable the local HTTP "
    "API (Settings -> Advanced). The /api/ endpoint is read-only/GET-only."
)


class ZoteroService:
    """Read-only access to the Zotero local API, honoring the library selector."""

    def __init__(self, http: HttpClient, endpoints: Optional[Endpoints] = None,
                 capability: Optional[CapabilityReport] = None) -> None:
        self.http = http
        self.endpoints = endpoints or Endpoints()
        self.capability = capability

    # ---- internals -------------------------------------------------------
    def _url(self, base: str, *parts: str) -> str:
        root = self.endpoints.zotero_api.rstrip("/")
        segs = [root, base, *parts]
        return "/".join(s.strip("/") for s in segs)

    def _provenance(self, tool: str, library: Any) -> Provenance:
        return Provenance(
            tool=tool, tool_version=__version__, ran_at=utc_now_iso(),
            config_hash=config_hash({"zotero_api": self.endpoints.zotero_api,
                                     "library": str(library)}),
            sources=[{"kind": "zotero_api", "detail": self.endpoints.zotero_api}],
        )

    def _unavailable(self) -> bool:
        # If a probe report is present, honor it; never assume availability.
        return self.capability is not None and not self.capability.available("zotero_api")

    def _get(self, url: str, params: Optional[dict] = None):
        return self.http.get(url, headers={"Host": "localhost:23119"}, params=params)

    def _group_ids(self) -> list[str]:
        resp = self._get(self._url("users/0", "groups"), params={"format": "json"})
        if resp.status_code != 200:
            return []
        out: list[str] = []
        for g in _as_list(resp.json()):
            gid = g.get("id") or (g.get("data") or {}).get("id")
            if gid is not None:
                out.append(str(gid))
        return out

    def _degrade(self, tool: str) -> ToolResult:
        return ToolResult.failure("zotero_unavailable",
                                  f"{tool}: Zotero local API unavailable",
                                  ZOTERO_UNREACHABLE_REMEDIATION)

    # ---- tools -----------------------------------------------------------
    def zot_search(self, query: str, library: LibrarySelector = "personal",
                   limit: Optional[int] = None) -> ToolResult:
        if self._unavailable():
            return self._degrade("zot_search")
        try:
            library = coerce_library(library)
            group_ids = self._group_ids() if library == "all" else None
            items: list[dict] = []
            for base in bases_for(library, group_ids):
                params: dict[str, Any] = {"q": query, "format": "json"}
                if limit:
                    params["limit"] = limit
                resp = self._get(self._url(base, "items"), params=params)
                if resp.status_code != 200:
                    return ToolResult.failure("zotero_http",
                                              f"zot_search: HTTP {resp.status_code} for {base}")
                items.extend(_summarize_item(it, base) for it in _as_list(resp.json()))
        except ProbeTransportError:
            return self._degrade("zot_search")
        except LibrarySelectorError as exc:
            return ToolResult.failure("library_selector", str(exc))
        return ToolResult(ok=True, data=items, provenance=self._provenance("zot_search", library))

    def zot_item(self, ref: ItemRef) -> ToolResult:
        if self._unavailable():
            return self._degrade("zot_item")
        try:
            base = base_path(ref.library)
            resp = self._get(self._url(base, "items", ref.zotero_key),
                             params={"format": "json"})
            if resp.status_code == 404:
                return ToolResult.failure("not_found",
                                          f"item {ref.zotero_key!r} not found in {base}")
            if resp.status_code != 200:
                return ToolResult.failure("zotero_http", f"zot_item: HTTP {resp.status_code}")
            body = resp.json()
            data = body[0] if isinstance(body, list) else body
        except ProbeTransportError:
            return self._degrade("zot_item")
        except LibrarySelectorError as exc:
            return ToolResult.failure("library_selector", str(exc))
        return ToolResult(ok=True, data=_summarize_item(data, base),
                          provenance=self._provenance("zot_item", ref.library))

    def zot_collections(self, library: LibrarySelector = "personal") -> ToolResult:
        if self._unavailable():
            return self._degrade("zot_collections")
        try:
            library = coerce_library(library)
            group_ids = self._group_ids() if library == "all" else None
            cols: list[dict] = []
            for base in bases_for(library, group_ids):
                resp = self._get(self._url(base, "collections"), params={"format": "json"})
                if resp.status_code != 200:
                    return ToolResult.failure("zotero_http",
                                              f"zot_collections: HTTP {resp.status_code}")
                for c in _as_list(resp.json()):
                    d = c.get("data") or {}
                    cols.append({"key": c.get("key"), "name": d.get("name"), "base": base})
        except ProbeTransportError:
            return self._degrade("zot_collections")
        except LibrarySelectorError as exc:
            return ToolResult.failure("library_selector", str(exc))
        return ToolResult(ok=True, data=cols,
                          provenance=self._provenance("zot_collections", library))

    def zot_attachments(self, ref: ItemRef) -> ToolResult:
        if self._unavailable():
            return self._degrade("zot_attachments")
        try:
            base = base_path(ref.library)
            resp = self._get(self._url(base, "items", ref.zotero_key, "children"),
                             params={"format": "json"})
            if resp.status_code != 200:
                return ToolResult.failure("zotero_http",
                                          f"zot_attachments: HTTP {resp.status_code}")
            atts = []
            for c in _as_list(resp.json()):
                d = c.get("data") or {}
                if d.get("itemType") == "attachment":
                    atts.append({"key": c.get("key"), "title": d.get("title"),
                                 "contentType": d.get("contentType"),
                                 "linkMode": d.get("linkMode"), "base": base})
        except ProbeTransportError:
            return self._degrade("zot_attachments")
        except LibrarySelectorError as exc:
            return ToolResult.failure("library_selector", str(exc))
        return ToolResult(ok=True, data=atts,
                          provenance=self._provenance("zot_attachments", ref.library))

    def _first_attachment_key(self, base: str, item_key: str) -> Optional[str]:
        resp = self._get(self._url(base, "items", item_key, "children"),
                         params={"format": "json"})
        if resp.status_code != 200:
            return None
        pdf = None
        first = None
        for c in _as_list(resp.json()):
            d = c.get("data") or {}
            if d.get("itemType") == "attachment":
                first = first or c.get("key")
                if d.get("contentType") == "application/pdf":
                    pdf = pdf or c.get("key")
        return pdf or first

    def zot_fulltext(self, ref: ItemRef, attachment_key: Optional[str] = None) -> ToolResult:
        """Read indexed full text for an item's attachment (read-only)."""
        if self._unavailable():
            return self._degrade("zot_fulltext")
        try:
            base = base_path(ref.library)
            akey = attachment_key or self._first_attachment_key(base, ref.zotero_key)
            if akey is None:
                return ToolResult.failure("full_text_unavailable",
                                          "zot_fulltext: no attachment found for item")
            resp = self._get(self._url(base, "items", akey, "fulltext"),
                             params={"format": "json"})
            if resp.status_code == 404:
                return ToolResult.failure("full_text_unavailable",
                                          "zot_fulltext: no indexed full text")
            if resp.status_code != 200:
                return ToolResult.failure("zotero_http", f"zot_fulltext: HTTP {resp.status_code}")
            body = resp.json()
            data = {
                "attachment_key": akey,
                "content": (body or {}).get("content", ""),
                "indexed_chars": (body or {}).get("indexedChars"),
                "total_chars": (body or {}).get("totalChars"),
                "indexed_pages": (body or {}).get("indexedPages"),
            }
        except ProbeTransportError:
            return self._degrade("zot_fulltext")
        except LibrarySelectorError as exc:
            return ToolResult.failure("library_selector", str(exc))
        return ToolResult(ok=True, data=data,
                          provenance=self._provenance("zot_fulltext", ref.library))

    def zot_annotations(self, ref: ItemRef, attachment_key: Optional[str] = None) -> ToolResult:
        """Read annotations (read-only). Locators come from annotation metadata."""
        if self._unavailable():
            return self._degrade("zot_annotations")
        try:
            base = base_path(ref.library)
            akey = attachment_key or self._first_attachment_key(base, ref.zotero_key)
            if akey is None:
                return ToolResult(ok=True, data=[],
                                  provenance=self._provenance("zot_annotations", ref.library))
            resp = self._get(self._url(base, "items", akey, "children"),
                             params={"format": "json"})
            if resp.status_code != 200:
                return ToolResult.failure("zotero_http", f"zot_annotations: HTTP {resp.status_code}")
            anns = []
            for c in _as_list(resp.json()):
                d = c.get("data") or {}
                if d.get("itemType") != "annotation":
                    continue
                anns.append({
                    "key": c.get("key"),
                    "text": d.get("annotationText", ""),
                    "comment": d.get("annotationComment"),
                    "page_label": d.get("annotationPageLabel"),
                    "page_index": _annotation_page_index(d.get("annotationPosition")),
                    "attachment_key": akey,
                })
        except ProbeTransportError:
            return self._degrade("zot_annotations")
        except LibrarySelectorError as exc:
            return ToolResult.failure("library_selector", str(exc))
        return ToolResult(ok=True, data=anns,
                          provenance=self._provenance("zot_annotations", ref.library))


def _annotation_page_index(position) -> Optional[int]:
    """Parse pageIndex from an annotationPosition (JSON string or dict). None if absent."""
    import json
    if position is None:
        return None
    if isinstance(position, str):
        try:
            position = json.loads(position)
        except Exception:
            return None
    if isinstance(position, dict):
        idx = position.get("pageIndex")
        return idx if isinstance(idx, int) else None
    return None


def _as_list(body: Any) -> list[dict]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        return [body]
    return []


def _summarize_item(item: dict, base: str) -> dict:
    data = item.get("data") or {}
    return {
        "key": item.get("key") or data.get("key"),
        "itemType": data.get("itemType"),
        "title": data.get("title"),
        "date": data.get("date"),
        "creators": data.get("creators", []),
        "DOI": data.get("DOI"),
        "base": base,
    }
