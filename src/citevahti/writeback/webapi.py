"""Live Zotero Web API write backend (api.zotero.org).

Scope: item creation (item_add, intake_push), with optional collection
assignment at creation time (POST only -- no PATCH). This is exactly what is
needed to add references into a collection. Operations that modify existing
items (collection_add_item, tag_add/remove, tag_mirror) or that need content not
present in the guarded operation (note/annotation bodies are hashed, not stored)
cleanly raise WriteUnavailable rather than write something partial.

The API key is supplied by the caller (read from env in make_backend); it is
never logged or persisted. All guarding (dry-run, one-use token, audit, no
silent fallback) lives in WriteLayer -- this class only performs the write.
"""

from __future__ import annotations

import re
from typing import Optional

from ..probe.client import HttpClient, ProbeTransportError
from ..schemas.writeback import WriteOperation
from .backend import WriteUnavailable

_CREATE_KINDS = {"item_add", "intake_push"}


class WebApiWriteBackend:
    kind = "web_api"
    available = True

    def __init__(self, http: HttpClient, api_key: str, user_id: str,
                 base: str = "https://api.zotero.org") -> None:
        self.http = http
        self.api_key = api_key
        self.user_id = str(user_id)
        self.base = base.rstrip("/")

    # ---- helpers ---------------------------------------------------------
    def _headers(self) -> dict:
        return {"Zotero-API-Key": self.api_key, "Zotero-API-Version": "3",
                "Content-Type": "application/json"}

    def _library_path(self, library: str) -> str:
        # personal/all -> the user's library; group selectors map best-effort.
        if isinstance(library, str) and library.startswith("group"):
            gid = library.split(":", 1)[1] if ":" in library else None
            if gid:
                return f"groups/{gid}"
        return f"users/{self.user_id}"

    @staticmethod
    def _creators(authors) -> list[dict]:
        out = []
        for a in authors or []:
            a = (a or "").strip()
            if not a:
                continue
            if " " in a:
                first, last = a.rsplit(" ", 1)
                out.append({"creatorType": "author", "firstName": first, "lastName": last})
            else:
                out.append({"creatorType": "author", "name": a})
        return out

    def _item_template(self, c: dict, collection_key: Optional[str]) -> dict:
        date = c.get("publication_date") or (str(c["year"]) if c.get("year") else "")
        item = {
            "itemType": "journalArticle",
            "title": c.get("title") or "",
            "creators": self._creators(c.get("authors")),
            "publicationTitle": c.get("journal") or "",
            "date": date,
            "DOI": c.get("doi") or "",
        }
        extra = []
        if c.get("pmid"):
            extra.append(f"PMID: {c['pmid']}")
        if extra:
            item["extra"] = "\n".join(extra)
        if collection_key:
            item["collections"] = [collection_key]
        return item

    def supports(self, kind: str) -> bool:
        return kind in _CREATE_KINDS

    def undo(self, undo_snapshot: dict) -> dict:
        """Reverse a committed creation by deleting ONLY the keys we created.

        Constrained + auditable: deletes exactly the ``delete_keys`` recorded in
        the transaction's undo_snapshot — never arbitrary items. Each delete reads
        the item's current version and sends it via ``If-Unmodified-Since-Version``
        so a user edit since creation aborts the delete (HTTP 412) rather than
        clobbering it.
        """
        keys = list(undo_snapshot.get("delete_keys") or [])
        library = undo_snapshot.get("library") or "personal"
        base = f"{self.base}/{self._library_path(library)}/items"
        deleted, skipped = [], []
        for key in keys:
            try:
                ver = self._item_version(base, key)
                if ver is None:
                    skipped.append({"key": key, "reason": "not_found_or_no_version"})
                    continue
                resp = self.http.delete(f"{base}/{key}",
                                        headers={**self._headers(),
                                                 "If-Unmodified-Since-Version": str(ver)})
            except ProbeTransportError as exc:
                raise WriteUnavailable(f"Zotero Web API unreachable during undo: {exc}") from exc
            if resp.status_code in (200, 204):
                deleted.append(key)
            elif resp.status_code == 412:     # modified since create -> never clobber a user edit
                skipped.append({"key": key, "reason": "modified_since_create"})
            else:
                skipped.append({"key": key, "reason": f"http_{resp.status_code}"})
        return {"backend": "web_api", "deleted_keys": deleted, "deleted": len(deleted),
                "skipped": skipped}

    def find_existing(self, pmid, doi, library: str = "personal"):
        """Item keys in the WRITE-target library matching pmid/doi.

        Searches the SAME library the write will target (personal or group:<id>) --
        not always personal -- so group writes are deduped against the group. Catches
        duplicates the local Zotero API can't see yet (Web-API-created items not synced
        locally). Returns [] if verified absent, or None if the search could not run
        (so callers degrade honestly instead of blocking).
        """
        from ..intake.dedupe import normalize_doi, normalize_pmid
        np, nd = normalize_pmid(pmid), normalize_doi(doi)
        if not (np or nd):
            return []
        base = f"{self.base}/{self._library_path(library)}/items"
        keys: list[str] = []
        for term in filter(None, [doi, pmid]):
            try:
                resp = self.http.get(base, headers=self._headers(),
                                     params={"q": term, "qmode": "everything", "format": "json",
                                             "itemType": "-attachment", "limit": "25"})
            except ProbeTransportError:
                return None                       # could not check -> unknown
            if resp.status_code != 200:
                return None
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                return None
            for it in (body if isinstance(body, list) else [body]):
                data = it.get("data") or it
                key = it.get("key") or data.get("key")
                doi_match = nd and normalize_doi(data.get("DOI")) == nd
                pmid_match = np and bool(re.search(rf"PMID:\s*{re.escape(np)}\b", data.get("extra", "") or ""))
                if key and (doi_match or pmid_match) and key not in keys:
                    keys.append(key)
        return keys

    def _item_version(self, base: str, key: str):
        resp = self.http.get(f"{base}/{key}", headers=self._headers(), params={"format": "json"})
        if resp.status_code != 200:
            return None
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            return None
        data = body[0] if isinstance(body, list) else body
        return (data or {}).get("version") or ((data or {}).get("data") or {}).get("version")

    # ---- apply -----------------------------------------------------------
    def apply(self, operation: WriteOperation) -> dict:
        if operation.kind not in _CREATE_KINDS:
            raise WriteUnavailable(
                f"operation {operation.kind!r} is not supported by the web_api backend yet "
                "(only item creation: item_add / intake_push). It modifies existing items or "
                "needs content not present in the guarded operation.")
        return self._create_items(operation)

    def _create_items(self, op: WriteOperation) -> dict:
        creates = op.structured.get("create") or []
        collection_key = op.structured.get("collection_key")
        skipped = len(op.structured.get("skipped") or [])
        if not creates:
            return {"backend": "web_api", "op": op.kind, "created_keys": [], "created": 0,
                    "skipped": skipped, "collection_key": collection_key}
        templates = [self._item_template(c, collection_key) for c in creates]
        url = f"{self.base}/{self._library_path(op.library)}/items"
        try:
            resp = self.http.post(url, json=templates, headers=self._headers())
        except ProbeTransportError as exc:
            raise WriteUnavailable(f"Zotero Web API unreachable: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise WriteUnavailable(f"Zotero Web API write failed: HTTP {resp.status_code}")
        try:
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise WriteUnavailable(f"Zotero Web API returned non-JSON: {exc}") from exc
        successful = (body or {}).get("successful") or {}
        created_keys = [v.get("key") for v in successful.values()
                        if isinstance(v, dict) and v.get("key")]
        failed = (body or {}).get("failed") or {}
        return {"backend": "web_api", "op": op.kind, "created_keys": created_keys,
                "created": len(created_keys), "failed": len(failed),
                "skipped": skipped, "collection_key": collection_key}
