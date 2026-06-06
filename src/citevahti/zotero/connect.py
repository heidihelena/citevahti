"""Guided one-paste Zotero connection (ADR-0005).

The researcher should never hand-craft an API key. CiteVahti opens Zotero's
new-key page **pre-filled** (name + write access), the user clicks Save and pastes
the key once; we validate it against the Web API, learn the userID automatically,
and store the key in the OS keychain. Reads stay keyless/local; this only enables
the guarded, decision-gated write-back.

The key is never written to config, logged, or echoed back.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

from ..credentials import ZOTERO_WRITE_KEY, get_credential_store

NEW_KEY_PAGE = "https://www.zotero.org/settings/keys/new"
DEFAULT_KEY_NAME = "CiteVahti"


_GROUP_LEVELS = ("none", "read", "write")


def new_key_url(name: str = DEFAULT_KEY_NAME, *, groups: str = "none") -> str:
    """The Zotero new-key page, pre-filled with personal write permission.

    ``groups`` (none|read|write) pre-selects access to *all* groups for users who
    write to shared/group libraries; default is personal-only (the user can still
    tick individual groups on the page). The user clicks **Save** and copies the key.
    """
    params = {"name": name, "library_access": 1, "notes_access": 1, "write_access": 1}
    if groups in ("read", "write"):
        # best-effort prefill; Zotero also lets the user choose groups on the page
        params["all_groups"] = groups
    return f"{NEW_KEY_PAGE}?{urlencode(params)}"


class ZoteroConnectError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ZoteroConnectService:
    """Validate a pasted key, learn the userID, store the key, enable web_api write."""

    def __init__(self, store, *, http=None, credential_store=None,
                 api_base: Optional[str] = None) -> None:
        self.store = store
        self._http = http
        self._cred = credential_store
        self._api_base = api_base

    def _client(self):
        if self._http is not None:
            return self._http
        from ..probe.client import HttpxClient
        return HttpxClient(timeout=8.0)

    def _base(self) -> str:
        if self._api_base:
            return self._api_base.rstrip("/")
        try:
            return (self.store.load_config().writeback.web_api_base or "https://api.zotero.org").rstrip("/")
        except Exception:  # noqa: BLE001
            return "https://api.zotero.org"

    # ---- key validation --------------------------------------------------
    def validate_key(self, api_key: str) -> dict:
        """Ask the Web API who this key belongs to and what it can do.

        Returns {user_id, username, write, library}. Raises ZoteroConnectError on
        an invalid key or an unreachable API. The key value is never returned.
        """
        api_key = (api_key or "").strip()
        if not api_key:
            raise ZoteroConnectError("empty_key", "no key was provided")
        from ..probe.client import ProbeTransportError

        url = f"{self._base()}/keys/current"
        headers = {"Zotero-API-Key": api_key, "Zotero-API-Version": "3"}
        try:
            resp = self._client().get(url, headers=headers)
        except ProbeTransportError as exc:
            raise ZoteroConnectError(
                "api_unreachable",
                f"could not reach the Zotero API ({exc}); check your connection") from exc
        if resp.status_code in (401, 403):
            raise ZoteroConnectError(
                "invalid_key",
                "Zotero rejected that key. Re-create it (the link opens the page pre-filled) "
                "and paste the new one.")
        if resp.status_code != 200:
            raise ZoteroConnectError(
                "unexpected_status", f"Zotero returned HTTP {resp.status_code} validating the key")
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ZoteroConnectError("bad_response", "could not parse the Zotero key response") from exc

        access = data.get("access") or {}
        user_access = access.get("user") or {}
        group_access = access.get("groups") or {}
        personal_write = bool(user_access.get("write"))
        groups = [{"id": gid, "write": bool(g.get("write"))}
                  for gid, g in group_access.items() if isinstance(g, dict)]
        group_write = [g["id"] for g in groups if g["write"]]
        return {
            "user_id": str(data.get("userID")) if data.get("userID") is not None else None,
            "username": data.get("username"),
            "personal_write": personal_write,
            "personal_library": bool(user_access.get("library", True)),
            "groups_total": len(groups),
            "groups_write": len(group_write),
            "write": personal_write or bool(group_write),
        }

    # ---- connect ---------------------------------------------------------
    def connect(self, api_key: str, *, require_write: bool = True) -> dict:
        """Validate, store the key, and enable guarded web_api write-back.

        Returns a result dict (never the key). On a read-only key it refuses by
        default, since the whole point is write-back."""
        info = self.validate_key(api_key)
        if not info["user_id"]:
            raise ZoteroConnectError("no_user_id", "the key validated but carried no userID")
        if require_write and not info["write"]:
            raise ZoteroConnectError(
                "no_write_access",
                "that key is read-only. Re-create it with write access (the link pre-checks it) "
                "and paste the new one.")

        cfg = self.store.load_config()
        backend = cfg.secrets_backend
        cred = self._cred or get_credential_store(backend)
        cred.set_secret(ZOTERO_WRITE_KEY, api_key.strip())   # OS keychain; never config

        # non-secret identifiers + enable the guarded web_api backend
        cfg.zotero.user_id = info["user_id"]
        cfg.writeback.web_api_user_id = info["user_id"]
        cfg.writeback.enabled = True
        cfg.writeback.kind = "web_api"
        cfg.writeback.web_api = "opt_in"
        self.store.save_config(cfg)

        return {
            "connected": True,
            "user_id": info["user_id"],
            "username": info["username"],
            "write_access": info["write"],
            "personal_write": info["personal_write"],
            "groups_total": info["groups_total"],
            "groups_write": info["groups_write"],
            "secrets_backend": getattr(cred, "backend", backend),
            "note": "key stored in the OS keychain; reads stay keyless. Writes remain "
                    "decision-gated, previewed, and undoable.",
        }
