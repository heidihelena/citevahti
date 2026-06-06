"""Write backends. Only a fake (tests) and a clearly-degraded live default.

A real local-add-on or Web-API writer would implement ``apply``. CiteVahti does
not infer Web API credentials or make network write calls unless explicitly
configured; the default live backend is ``UnavailableBackend`` (dry-run previews
still work; confirmed writes fail cleanly).
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..schemas.writeback import WriteOperation


class WriteUnavailable(Exception):
    code = "write_layer_unavailable"


# Every write operation kind the tool surface can construct. The capability
# screen lists which of these the *configured* backend actually supports, so the
# UI/CLI never previews an op the backend would reject.
ALL_WRITE_KINDS = (
    "item_add", "intake_push", "note_add", "annotation_add",
    "tag_add", "tag_remove", "collection_add_item", "tag_mirror",
)


@runtime_checkable
class WriteBackend(Protocol):
    kind: str
    available: bool

    def apply(self, operation: WriteOperation) -> dict: ...

    def supports(self, kind: str) -> bool: ...

    def undo(self, undo_snapshot: dict) -> dict: ...

    # Returns item keys already in the WRITE TARGET matching pmid/doi, [] if none,
    # or None if existence could not be checked. Used to catch duplicates across
    # the local-Zotero / Web-API sync boundary before a write.
    def find_existing(self, pmid, doi) -> "Optional[list[str]]": ...


class UnavailableBackend:
    """A backend that previews but never writes (no configured endpoint)."""

    available = False

    def __init__(self, kind: str = "unavailable", reason: Optional[str] = None) -> None:
        self.kind = kind
        self.reason = reason or (
            "No Zotero write backend is configured. Set writeback.enabled and a real "
            "writeback.kind (local_addon or web_api) with a configured endpoint/credentials.")

    def apply(self, operation: WriteOperation) -> dict:
        raise WriteUnavailable(self.reason)

    def supports(self, kind: str) -> bool:
        # Nothing is live, but it's "unavailable", not "unsupported": availability
        # is checked first, so this value is never the user-facing reason.
        return False

    def undo(self, undo_snapshot: dict) -> dict:
        raise WriteUnavailable(self.reason)

    def find_existing(self, pmid, doi):
        return None        # an unconfigured backend cannot check the write target


class FakeWriteBackend:
    """Deterministic in-memory backend for tests (records every applied op).

    ``existing`` seeds a fake write-target library: a list of dicts with any of
    ``pmid`` / ``doi`` / ``key`` so ``find_existing`` can report cross-boundary
    duplicates deterministically.
    """

    available = True

    def __init__(self, kind: str = "local_addon", existing=None) -> None:
        from ..intake.dedupe import normalize_doi, normalize_pmid
        self.kind = kind
        self.applied: list[WriteOperation] = []
        self.undone: list[dict] = []
        self._by_pmid, self._by_doi = {}, {}
        for i, e in enumerate(existing or []):
            key = e.get("key") or f"EXIST{i}"
            if normalize_pmid(e.get("pmid")):
                self._by_pmid[normalize_pmid(e.get("pmid"))] = key
            if normalize_doi(e.get("doi")):
                self._by_doi[normalize_doi(e.get("doi"))] = key

    def supports(self, kind: str) -> bool:
        return True

    def find_existing(self, pmid, doi):
        from ..intake.dedupe import normalize_doi, normalize_pmid
        keys = []
        np, nd = normalize_pmid(pmid), normalize_doi(doi)
        if np and np in self._by_pmid:
            keys.append(self._by_pmid[np])
        if nd and nd in self._by_doi and self._by_doi[nd] not in keys:
            keys.append(self._by_doi[nd])
        return keys

    def apply(self, operation: WriteOperation) -> dict:
        self.applied.append(operation)
        created = operation.structured.get("create") or []
        return {"backend": self.kind, "op": operation.kind,
                "targets": operation.targets,
                "created_keys": [f"NEW{operation.kind[:3].upper()}{i}" for i in range(len(created))]}

    def undo(self, undo_snapshot: dict) -> dict:
        self.undone.append(undo_snapshot)
        keys = list(undo_snapshot.get("delete_keys") or [])
        return {"backend": self.kind, "deleted_keys": keys, "deleted": len(keys)}


def make_backend(config) -> WriteBackend:
    """Pick the single configured backend. Never returns a fallback chain."""
    import os

    wb = config.writeback
    if not wb.enabled or wb.kind == "unavailable":
        return UnavailableBackend(kind=wb.kind)

    if wb.kind == "web_api":
        from ..credentials import ZOTERO_WRITE_KEY, get_credential_store, resolve_secret
        from ..probe.client import HttpxClient
        from .webapi import WebApiWriteBackend
        # secret: env escape hatch -> OS keyring (never from config)
        try:
            cred_store = get_credential_store(getattr(config, "secrets_backend", "system_keyring"))
        except Exception:  # noqa: BLE001 (keyring missing)
            cred_store = None
        api_key = resolve_secret(ZOTERO_WRITE_KEY, cred_store)
        user_id = (config.zotero.library_id or config.zotero.user_id or wb.web_api_user_id
                   or os.environ.get("ZOTERO_USER_ID"))
        if not api_key or not user_id:
            # Missing credentials -> unavailable. We do NOT fall back to anything.
            return UnavailableBackend(
                kind="web_api",
                reason=("web_api enabled but missing credentials: run `citevahti onboard` (stores the "
                        "Zotero write key in the OS keyring) or set $CITEVAHTI_ZOTERO_WRITE_KEY, and "
                        "set the Zotero user id. No silent fallback."))
        return WebApiWriteBackend(HttpxClient(), api_key, str(user_id), base=wb.web_api_base)

    # local_addon (and anything else): Zotero's local /api/ is read-only -- there is no
    # live write endpoint. Explicitly unavailable; never fall back to web_api.
    return UnavailableBackend(
        kind=wb.kind,
        reason=f"writeback.kind={wb.kind!r} has no live write endpoint (Zotero local /api/ is "
               "read-only); no silent fallback is performed.")
