"""Credential resolution: env escape hatch precedence, store fallback, no leaks."""

from citevahti.credentials import (
    NCBI_API_KEY,
    ZOTERO_WRITE_KEY,
    InMemoryCredentialStore,
    KeyringCredentialStore,
    get_credential_store,
    resolve_secret,
    secret_source,
)


def test_inmemory_store_set_get_delete():
    s = InMemoryCredentialStore()
    s.set_secret(ZOTERO_WRITE_KEY, "v")
    assert s.get_secret(ZOTERO_WRITE_KEY) == "v"
    s.delete_secret(ZOTERO_WRITE_KEY)
    assert s.get_secret(ZOTERO_WRITE_KEY) is None


def test_env_overrides_store(monkeypatch):
    store = InMemoryCredentialStore({ZOTERO_WRITE_KEY: "from-store"})
    monkeypatch.setenv("CITEVAHTI_ZOTERO_WRITE_KEY", "from-env")
    assert resolve_secret(ZOTERO_WRITE_KEY, store) == "from-env"   # env wins


def test_store_used_when_no_env(monkeypatch):
    monkeypatch.delenv("CITEVAHTI_ZOTERO_WRITE_KEY", raising=False)
    store = InMemoryCredentialStore({ZOTERO_WRITE_KEY: "from-store"})
    assert resolve_secret(ZOTERO_WRITE_KEY, store) == "from-store"


def test_unset_returns_none(monkeypatch):
    monkeypatch.delenv("CITEVAHTI_NCBI_API_KEY", raising=False)
    assert resolve_secret(NCBI_API_KEY, InMemoryCredentialStore()) is None


def test_secret_source_labels(monkeypatch):
    monkeypatch.delenv("CITEVAHTI_ZOTERO_WRITE_KEY", raising=False)
    store = InMemoryCredentialStore({ZOTERO_WRITE_KEY: "v"})
    assert secret_source(ZOTERO_WRITE_KEY, store).startswith("memory:CiteVahti/")
    monkeypatch.setenv("CITEVAHTI_ZOTERO_WRITE_KEY", "v")
    assert secret_source(ZOTERO_WRITE_KEY, store) == "env:CITEVAHTI_ZOTERO_WRITE_KEY"


def test_get_credential_store_backends():
    assert isinstance(get_credential_store("env"), InMemoryCredentialStore)
    # keyring is installed in this environment; constructing must not write anything
    assert isinstance(get_credential_store("system_keyring"), KeyringCredentialStore)
