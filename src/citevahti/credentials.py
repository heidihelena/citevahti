"""Secure credential handling for CiteVahti.

Secrets (the Zotero write key, the NCBI API key) are **never** written to
config.json, .env-in-git, logs, or any CiteVahti state file. They live in the OS
credential store via ``keyring`` (macOS Keychain / Windows Credential Locker /
Freedesktop Secret Service / KWallet), under service name ``CiteVahti``.

Runtime resolution order: **environment variable (escape hatch) -> keyring**.
The env vars are for runtime injection (CI/headless) only, not persistence.
"""

from __future__ import annotations

import os
from typing import Optional, Protocol, runtime_checkable

SERVICE = "CiteVahti"

# keyring secret names
ZOTERO_WRITE_KEY = "zotero_write_key"
NCBI_API_KEY = "ncbi_api_key"
FULLVAHTI_TOKEN = "fullvahti_token"      # noqa: S105 — keyring lookup-key name, not a secret value; the FullVahti plugin's local tag-write token
AI_API_KEY = "ai_api_key"                # external AI provider key (api mode only; local needs none)

# env escape hatches (runtime injection only; override the keyring)
ENV_FOR_SECRET = {
    ZOTERO_WRITE_KEY: "CITEVAHTI_ZOTERO_WRITE_KEY",
    NCBI_API_KEY: "CITEVAHTI_NCBI_API_KEY",
    FULLVAHTI_TOKEN: "CITEVAHTI_FULLVAHTI_TOKEN",
    AI_API_KEY: "CITEVAHTI_AI_API_KEY",
}

SECRET_NAMES = tuple(ENV_FOR_SECRET)


class CredentialError(Exception):
    code = "credential_error"


@runtime_checkable
class CredentialStore(Protocol):
    backend: str

    def get_secret(self, name: str) -> Optional[str]: ...
    def set_secret(self, name: str, value: str) -> None: ...
    def delete_secret(self, name: str) -> None: ...


class KeyringCredentialStore:
    """OS-native secret store via the ``keyring`` package."""

    backend = "system_keyring"

    def __init__(self) -> None:
        try:
            import keyring  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise CredentialError(
                "the 'keyring' package is required for system_keyring storage; "
                "install it (e.g. `pip install keyring`) or use env vars "
                "CITEVAHTI_ZOTERO_WRITE_KEY / CITEVAHTI_NCBI_API_KEY.") from exc

    def get_secret(self, name: str) -> Optional[str]:
        import keyring
        try:
            return keyring.get_password(SERVICE, name)
        except Exception as exc:  # noqa: BLE001 (keyring.errors.KeyringError, e.g. macOS -50)
            raise CredentialError(
                "Credential store unavailable (the OS keychain could not be read). "
                "Use an env key (CITEVAHTI_ZOTERO_WRITE_KEY / CITEVAHTI_NCBI_API_KEY) or "
                "re-onboard.") from exc

    def set_secret(self, name: str, value: str) -> None:
        import keyring
        try:
            keyring.set_password(SERVICE, name, value)
        except Exception as exc:  # noqa: BLE001
            raise CredentialError(
                "Credential store unavailable (the OS keychain could not be written). "
                "Use the env backend (--backend env) or set the CITEVAHTI_* env vars.") from exc

    def delete_secret(self, name: str) -> None:
        import keyring
        try:
            keyring.delete_password(SERVICE, name)
        except Exception:  # noqa: BLE001
            pass


class InMemoryCredentialStore:
    """Non-persistent store for tests and ``secrets_backend='env'`` (no disk)."""

    backend = "memory"

    def __init__(self, initial: Optional[dict] = None) -> None:
        self._d = dict(initial or {})

    def get_secret(self, name: str) -> Optional[str]:
        return self._d.get(name)

    def set_secret(self, name: str, value: str) -> None:
        self._d[name] = value

    def delete_secret(self, name: str) -> None:
        self._d.pop(name, None)


def get_credential_store(backend: str = "system_keyring") -> CredentialStore:
    if backend == "system_keyring":
        return KeyringCredentialStore()
    return InMemoryCredentialStore()


def resolve_secret(name: str, store: Optional[CredentialStore] = None) -> Optional[str]:
    """Resolve a secret: env escape hatch first, then the credential store.

    Never logs the value. Returns None if unset.
    """
    env_var = ENV_FOR_SECRET.get(name)
    if env_var:
        val = os.environ.get(env_var)
        if val:
            return val
    if store is not None:
        try:
            return store.get_secret(name)
        except CredentialError:
            return None
    return None


def secret_source(name: str, store: Optional[CredentialStore] = None) -> str:
    """Where a secret would resolve from (for status display; never the value)."""
    env_var = ENV_FOR_SECRET.get(name)
    if env_var and os.environ.get(env_var):
        return f"env:{env_var}"
    if store is not None:
        try:
            if store.get_secret(name):
                return f"{getattr(store, 'backend', 'store')}:{SERVICE}/{name}"
        except CredentialError:
            return "store_unavailable"
    return "unset"


def secret_state(name: str, store: Optional[CredentialStore] = None) -> str:
    """Coarse state for status display: configured | missing | store_unavailable.

    Honors the env escape hatch first, then the store. Never returns the value.
    """
    src = secret_source(name, store)
    if src == "unset":
        return "missing"
    if src == "store_unavailable":
        return "store_unavailable"
    return "configured"
