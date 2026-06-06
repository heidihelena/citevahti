"""Connection & Capabilities: a read-only, truth-telling status report.

This is the foundation a UI (or a human) should consult *before* trusting any
workflow. It answers, honestly and without leaking secrets:

  - Which connections are live (Zotero local API, Better BibTeX) and at what
    version, vs unavailable + why.
  - What is *configured* (PubMed email, NCBI key, Zotero Web API write key,
    Zotero user id) and where each secret resolves from -- never the value.
  - Which write operations the *configured backend can actually perform*, so the
    UI never advertises an op (e.g. ``note_add``) the backend would reject.

It performs only GETs (the probe) and credential-store reads; it never writes,
never mutates state, and never makes a Zotero write call.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .credentials import (
    NCBI_API_KEY,
    ZOTERO_WRITE_KEY,
    get_credential_store,
    secret_source,
    secret_state,
)
from .probe.client import HttpClient
from .writeback.backend import ALL_WRITE_KINDS, make_backend


class ConnectionState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    status: str                            # connected | unavailable | configured | missing | store_unavailable
    detail: Optional[str] = None
    version: Optional[str] = None
    secret_source: Optional[str] = None    # where it resolves from (never the value)
    remediation: Optional[str] = None


class CapabilitiesReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_version: str = __version__
    connections: list[ConnectionState] = Field(default_factory=list)
    secrets_backend: str = "system_keyring"
    zotero_user_id: Optional[str] = None
    write_backend_kind: str = "unavailable"
    write_backend_available: bool = False
    write_backend_reason: Optional[str] = None
    supported_write_ops: list[str] = Field(default_factory=list)
    unsupported_write_ops: list[str] = Field(default_factory=list)
    permissions: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    def get(self, name: str) -> Optional[ConnectionState]:
        return next((c for c in self.connections if c.name == name), None)


class CapabilityStatusService:
    """Build a CapabilitiesReport from a probe + config + credential store."""

    def __init__(self, store, http: HttpClient, endpoints=None) -> None:
        self.store = store
        self.http = http
        self.endpoints = endpoints

    def report(self) -> CapabilitiesReport:
        import os

        from .probe import run_probes

        cfg = self.store.load_config()
        rep = CapabilitiesReport(secrets_backend=getattr(cfg, "secrets_backend", "system_keyring"))

        # ---- live connections (GET-only probe) --------------------------
        probes = run_probes(self.http, self.endpoints)
        zot = probes.results.get("zotero_api")
        bbt = probes.results.get("bbt_ready")
        rep.connections.append(ConnectionState(
            name="zotero_local_api",
            status="connected" if (zot and zot.available) else "unavailable",
            detail=(zot.detail if zot else None), version=(zot.version if zot else None),
            remediation=(None if (zot and zot.available) else (zot.remediation if zot else None))))
        rep.connections.append(ConnectionState(
            name="better_bibtex",
            status="connected" if (bbt and bbt.available) else "unavailable",
            detail=(bbt.detail if bbt else None), version=(bbt.version if bbt else None),
            remediation=(None if (bbt and bbt.available) else (bbt.remediation if bbt else None))))

        # ---- PubMed / NCBI (config presence; not a live einfo call) ------
        email = os.environ.get(cfg.pubmed.email_env) or cfg.pubmed.contact_email
        rep.connections.append(ConnectionState(
            name="pubmed_ncbi",
            status="configured" if email else "missing",
            detail=("NCBI email set" if email else "NCBI email required for live PubMed queries"),
            remediation=(None if email else
                         f"Set ${cfg.pubmed.email_env} or run `citevahti onboard --ncbi-email ...`.")))

        # ---- secrets (state + source, never the value) ------------------
        try:
            cred_store = get_credential_store(rep.secrets_backend)
        except Exception:  # noqa: BLE001 (keyring import missing)
            cred_store = None
        rep.connections.append(self._secret_state("ncbi_api_key", NCBI_API_KEY, cred_store))
        rep.connections.append(self._secret_state("zotero_write_key", ZOTERO_WRITE_KEY, cred_store))

        rep.zotero_user_id = (cfg.zotero.library_id or cfg.zotero.user_id
                              or cfg.writeback.web_api_user_id or os.environ.get("ZOTERO_USER_ID"))

        # ---- write backend: REAL capability of the configured backend ---
        backend = make_backend(cfg)
        rep.write_backend_kind = backend.kind
        rep.write_backend_available = bool(backend.available)
        rep.write_backend_reason = getattr(backend, "reason", None)
        supports = getattr(backend, "supports", None)
        for kind in ALL_WRITE_KINDS:
            ok = bool(supports(kind)) if callable(supports) else False
            (rep.supported_write_ops if (backend.available and ok)
             else rep.unsupported_write_ops).append(kind)

        # ---- permissions (honest summary) -------------------------------
        rep.permissions = {
            "zotero_local_api": "read-only (GET-only)",
            "personal_library": ("read; write via web_api (item creation only)"
                                 if rep.write_backend_available else "read; no live write configured"),
            "groups": "read-only",
            "files_fulltext_annotations": "read",
        }
        if rep.write_backend_available and rep.unsupported_write_ops:
            rep.notes.append(
                "Write backend creates items only. Existing-item edits "
                f"({', '.join(rep.unsupported_write_ops)}) are previewed but not yet writable.")
        return rep

    def _secret_state(self, name: str, secret_key: str, cred_store) -> ConnectionState:
        state = secret_state(secret_key, cred_store)
        status = {"configured": "configured", "missing": "missing",
                  "store_unavailable": "store_unavailable"}[state]
        rem = None
        if state == "missing":
            rem = "Run `citevahti onboard` (OS keyring) or set the matching CITEVAHTI_* env var."
        elif state == "store_unavailable":
            rem = "OS keychain unreadable; use the env backend or the CITEVAHTI_* env var."
        return ConnectionState(name=name, status=status,
                               secret_source=secret_source(secret_key, cred_store), remediation=rem)
