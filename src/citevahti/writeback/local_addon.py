"""Local write backend via the FullVahti Zotero plugin's token-gated door.

Zotero's *built-in* local API is read-only, so CiteVahti can't write tags through
it. The **FullVahti** plugin (github.com/heidihelena/fullvahti) registers two
routes on Zotero's own local server (default ``127.0.0.1:23119``):

  * ``GET  /fullvahti/ping``  -> ``{version, writeback: bool}`` (availability)
  * ``POST /fullvahti/tag``   -> ``{token, itemKey, add:[tags], remove:[tags]}``

This backend writes **tags only** (``tag_add`` / ``tag_remove`` / ``tag_mirror``) —
the plugin does not create items. Item creation still goes through the Web API
backend. The token is local-only: this backend refuses to send it to a
non-loopback URL unless explicitly allowed. Same contract MatchVahti's
``vahtian_fulltext.py`` already uses, so the two tools write identically.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from ..probe.client import HttpClient, ProbeTransportError
from ..schemas.writeback import WriteOperation
from .backend import WriteUnavailable

_SUPPORTED_KINDS = frozenset({"tag_add", "tag_remove", "tag_mirror"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_loopback(url: str) -> bool:
    """True only for loopback hosts — the FullVahti token must never leave the machine."""
    host = (urlparse(url).hostname or "").strip().lower()
    return host in _LOOPBACK_HOSTS


class FullVahtiWriteBackend:
    """Tag write-back through the FullVahti plugin's ``/fullvahti/tag`` door."""

    kind = "local_addon"
    available = True

    def __init__(self, http: HttpClient, token: str,
                 base: str = "http://127.0.0.1:23119", *, allow_remote: bool = False) -> None:
        self.http = http
        self.token = token
        self.base = base.rstrip("/")
        if not allow_remote and not is_loopback(self.base):
            raise WriteUnavailable(
                f"refusing to send the FullVahti token to a non-loopback URL ({self.base!r}); "
                "the token is local-only. Use the Zotero local server, or set "
                "writeback.allow_remote_writeback to override at your own risk.")

    # ---- capability ------------------------------------------------------
    def supports(self, kind: str) -> bool:
        # FullVahti writes tags onto existing items; it does NOT create items.
        return kind in _SUPPORTED_KINDS

    def find_existing(self, pmid, doi):
        # tag writes target existing item keys, not new items — no dedupe to do here.
        return None

    def ping(self) -> dict:
        """Probe the door without writing. ``{reachable, writeback, version, message}``."""
        try:
            r = self.http.get(f"{self.base}/fullvahti/ping")
        except ProbeTransportError as e:
            return {"reachable": False, "writeback": False, "message": f"not reachable: {e}"}
        if r.status_code != 200:
            return {"reachable": False, "writeback": False, "message": f"ping HTTP {r.status_code}"}
        try:
            j = r.json()
        except Exception:  # noqa: BLE001
            return {"reachable": False, "writeback": False,
                    "message": "ping returned non-JSON — is the FullVahti plugin installed?"}
        return {"reachable": True, "writeback": bool(j.get("writeback")),
                "version": j.get("version"), "message": "ok"}

    # ---- write -----------------------------------------------------------
    def _post_tag(self, item_key: str, add: list, remove: list) -> None:
        try:
            r = self.http.post(f"{self.base}/fullvahti/tag",
                               json={"token": self.token, "itemKey": item_key,
                                     "add": list(add), "remove": list(remove)})
        except ProbeTransportError as e:
            raise WriteUnavailable(f"FullVahti door unreachable at {self.base}: {e}") from e
        if r.status_code != 200:
            body = (r.text or "").strip().splitlines()
            raise WriteUnavailable(
                f"FullVahti /tag HTTP {r.status_code}: {body[0][:160] if body else '(no body)'}")

    def _per_target_ops(self, operation: WriteOperation) -> list:
        """Normalise an op to ``[{itemKey, add, remove}]`` for the FullVahti door."""
        s = operation.structured or {}
        if operation.kind == "tag_add":
            add = s.get("add_tags", [])
            return [{"itemKey": k, "add": add, "remove": []} for k in operation.targets]
        if operation.kind == "tag_remove":
            remove = s.get("remove_tags", [])
            return [{"itemKey": k, "add": [], "remove": remove} for k in operation.targets]
        if operation.kind == "tag_mirror":
            return [{"itemKey": pt["zotero_key"], "add": pt.get("add", []),
                     "remove": pt.get("remove", [])} for pt in s.get("per_target", [])]
        raise WriteUnavailable(
            f"the FullVahti backend writes tags only (tag_add/tag_remove/tag_mirror); "
            f"it cannot perform {operation.kind!r}. Item creation uses the Web API backend.")

    def apply(self, operation: WriteOperation) -> dict:
        ops = self._per_target_ops(operation)
        for o in ops:
            self._post_tag(o["itemKey"], o["add"], o["remove"])
        return {"backend": self.kind, "op": operation.kind,
                "targets": [o["itemKey"] for o in ops], "applied": ops}

    def undo(self, undo_snapshot: dict) -> dict:
        """Reverse a tag write: swap add/remove for each recorded item."""
        ops = (undo_snapshot or {}).get("applied") or []
        for o in ops:
            # reverse: what was added is removed, what was removed is re-added
            self._post_tag(o["itemKey"], o.get("remove", []), o.get("add", []))
        return {"backend": self.kind, "reversed": len(ops),
                "keys": [o["itemKey"] for o in ops]}
