"""Guided onboarding: capture PubMed email, Zotero IDs, default collection, and
secret keys, routing each by sensitivity.

- Non-secret identifiers -> .citevahti/config.json.
- Secret keys (Zotero write key, NCBI key) -> the OS keyring (or env escape
  hatch). They are held in memory only, validated where possible, then stored,
  and NEVER written to config/logs or echoed back.
"""

from __future__ import annotations

from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .credentials import (
    FULLVAHTI_TOKEN,
    NCBI_API_KEY,
    ZOTERO_WRITE_KEY,
    CredentialStore,
    get_credential_store,
)


class OnboardingReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secrets_backend: str = "system_keyring"
    config_updated: list[str] = Field(default_factory=list)   # field names only
    secrets_stored: list[str] = Field(default_factory=list)   # secret NAMES only, never values
    secrets_skipped: list[str] = Field(default_factory=list)
    validations: dict = Field(default_factory=dict)           # name -> "ok"/"skipped"/"failed: ..."
    warnings: list[str] = Field(default_factory=list)


class CredentialValidators(Protocol):
    def validate_zotero_key(self, key: str, user_id: Optional[str]) -> tuple[bool, str, Optional[str]]:
        """Return (ok, detail, resolved_user_id)."""
        ...

    def validate_ncbi_key(self, key: str, email: Optional[str]) -> tuple[bool, str]: ...


class OnboardingService:
    def __init__(self, store, credential_store: Optional[CredentialStore] = None,
                 validators: Optional[CredentialValidators] = None) -> None:
        self.store = store
        self.credential_store = credential_store
        self.validators = validators

    def onboard(self, *, ncbi_email: Optional[str] = None, zotero_user_id: Optional[str] = None,
                zotero_library_id: Optional[str] = None, zotero_library_type: str = "user",
                default_collection_key: Optional[str] = None,
                zotero_write_key: Optional[str] = None, ncbi_api_key: Optional[str] = None,
                fullvahti_token: Optional[str] = None,
                enable_writeback: bool = True, validate: bool = True,
                secrets_backend: str = "system_keyring") -> OnboardingReport:
        report = OnboardingReport(secrets_backend=secrets_backend)
        cred = self.credential_store
        if cred is None and secrets_backend != "env":
            try:
                cred = get_credential_store(secrets_backend)
            except Exception as exc:  # noqa: BLE001 (keyring missing)
                report.warnings.append(f"secret store unavailable: {exc}")
        cfg = self.store.load_config()

        # ---- non-secret identifiers -> config -------------------------------
        if ncbi_email:
            cfg.pubmed.contact_email = ncbi_email
            report.config_updated.append("pubmed.contact_email")
        if zotero_user_id:
            cfg.zotero.user_id = zotero_user_id
            report.config_updated.append("zotero.user_id")
        cfg.zotero.library_type = zotero_library_type  # "user" | "group"
        # library_id = the ADDRESSED library (personal library == account user id, or the
        # group id). It is NOT the Web-API account user id used to build users/<id>; see
        # web_api_user_id below. Validating the write key reuses it (group when grouping).
        lib_id = zotero_library_id or zotero_user_id
        if lib_id:
            cfg.zotero.library_id = lib_id
            report.config_updated.append("zotero.library_id")
        # web_api_user_id addresses users/<id> -> it must be the ACCOUNT user id, never a
        # group id. A group target is expressed via default_library=group:<id> instead, so
        # personal-path ops can't accidentally build /users/<group-id>.
        if zotero_user_id:
            cfg.writeback.web_api_user_id = zotero_user_id
            report.config_updated.append("writeback.web_api_user_id")
        if zotero_library_type == "group" and zotero_library_id:
            from .schemas.common import GroupLibrary
            cfg.default_library = GroupLibrary(group_id=zotero_library_id)
            report.config_updated.append("default_library")
        if default_collection_key:
            cfg.zotero.default_collection_key = default_collection_key
            cfg.writeback.default_collection_key = default_collection_key
            report.config_updated.append("zotero.default_collection_key")
        cfg.secrets_backend = secrets_backend
        report.config_updated.append("secrets_backend")

        # ---- secrets: validate (in memory) then store to keyring -----------
        # backend 'env' means runtime injection only: we never persist the value.
        store_secrets = secrets_backend != "env"
        write_key_ready = False
        if zotero_write_key:
            if store_secrets:
                self._handle_secret(report, cred, ZOTERO_WRITE_KEY, zotero_write_key, validate,
                                     lambda k: (self.validators.validate_zotero_key(k, lib_id)
                                                if self.validators else (None, "skipped", None)))
                write_key_ready = ZOTERO_WRITE_KEY in report.secrets_stored
            else:
                report.validations[ZOTERO_WRITE_KEY] = "env-injected (not stored)"
                report.warnings.append("env backend: export $CITEVAHTI_ZOTERO_WRITE_KEY at runtime")
                write_key_ready = True
        if enable_writeback and write_key_ready:
            cfg.writeback.enabled = True
            cfg.writeback.kind = "web_api"
            report.config_updated += ["writeback.enabled", "writeback.kind"]
        if ncbi_api_key:
            if store_secrets:
                self._handle_secret(report, cred, NCBI_API_KEY, ncbi_api_key, validate,
                                     lambda k: ((*self.validators.validate_ncbi_key(k, ncbi_email
                                                or cfg.pubmed.contact_email), None)
                                                if self.validators else (None, "skipped", None)))
            else:
                report.validations[NCBI_API_KEY] = "env-injected (not stored)"
                report.warnings.append("env backend: export $CITEVAHTI_NCBI_API_KEY at runtime")

        # FullVahti plugin tag-write token (no live validation — verified by `status` ping).
        # web_api (item creation) takes precedence; FullVahti wires the local_addon backend
        # only when no Zotero write key was provided.
        fullvahti_ready = False
        if fullvahti_token:
            if store_secrets:
                self._handle_secret(report, cred, FULLVAHTI_TOKEN, fullvahti_token, validate,
                                     lambda k: (None, "skipped", None))
                fullvahti_ready = FULLVAHTI_TOKEN in report.secrets_stored
            else:
                report.validations[FULLVAHTI_TOKEN] = "env-injected (not stored)"
                report.warnings.append("env backend: export $CITEVAHTI_FULLVAHTI_TOKEN at runtime")
                fullvahti_ready = True
        if enable_writeback and fullvahti_ready and not write_key_ready and cfg.writeback.kind != "web_api":
            cfg.writeback.enabled = True
            cfg.writeback.kind = "local_addon"
            report.config_updated += ["writeback.enabled", "writeback.kind"]

        self.store.save_config(cfg)   # config carries NO secret values
        return report

    def _handle_secret(self, report, cred, name, value, validate, validate_fn) -> None:
        if validate and self.validators is not None:
            ok, detail, resolved = validate_fn(value)
            if ok is False:
                report.secrets_skipped.append(name)
                report.validations[name] = f"failed: {detail}"
                report.warnings.append(f"{name} not stored: validation failed ({detail})")
                return
            report.validations[name] = "ok" if ok else "skipped"
        else:
            report.validations[name] = "skipped"
            if validate:
                report.warnings.append(f"{name} stored without validation (no validators wired)")
        try:
            cred.set_secret(name, value)
        except Exception as exc:  # noqa: BLE001
            report.secrets_skipped.append(name)
            report.warnings.append(f"{name} could not be stored: {exc}")
            return
        report.secrets_stored.append(name)   # NAME only -- never the value


class LiveValidators:
    """Best-effort live validation of secret keys before they are stored.

    Network-unavailable validations return ok=None (treated as 'skipped', not a
    hard failure) so onboarding works offline; a key that is reachable but lacks
    the required permission returns ok=False and is NOT stored.
    """

    def __init__(self, http, zotero_base: str = "https://api.zotero.org") -> None:
        self.http = http
        self.zotero_base = zotero_base.rstrip("/")

    def validate_zotero_key(self, key: str, user_id):
        from .probe.client import ProbeTransportError
        try:
            r = self.http.get(f"{self.zotero_base}/keys/current",
                              headers={"Zotero-API-Key": key, "Zotero-API-Version": "3"})
        except ProbeTransportError:
            return None, "network unavailable; validation skipped", None
        if r.status_code != 200:
            return False, f"Zotero key check HTTP {r.status_code}", None
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            return None, "non-JSON response; validation skipped", None
        access = (body.get("access") or {}).get("user") or {}
        uid = str(body.get("userID")) if body.get("userID") else None
        if not (access.get("write") or access.get("library")):
            return False, "key has no write access to the user library", uid
        return True, "write access confirmed", uid

    def validate_ncbi_key(self, key: str, email):
        from .probe.client import ProbeTransportError
        try:
            r = self.http.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi",
                              params={"api_key": key, "email": email or "", "retmode": "json"})
        except ProbeTransportError:
            return None, "network unavailable; validation skipped"
        return (r.status_code == 200, f"einfo HTTP {r.status_code}")
