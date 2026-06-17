"""Keyring errors degrade gracefully -- they never crash a read like PubMed search.

Regression for the privacy-researcher blocker: a macOS `KeyringError(-50)` during
NCBI-key lookup crashed `literature_search`. The keyring store now raises a clean
`CredentialError`, which `resolve_secret` turns into None (keyless, not a crash).
"""

import pytest

# `keyring` is an optional extra (pip install citevahti[keyring]); these tests
# exercise the real keyring backend, so skip cleanly when it isn't installed.
pytest.importorskip("keyring")

from citevahti.credentials import (
    NCBI_API_KEY,
    CredentialError,
    KeyringCredentialStore,
    resolve_secret,
    secret_source,
    secret_state,
)


class BoomKeyring(KeyringCredentialStore):
    """A keyring store whose backend always errors (simulating Keychain -50)."""

    def __init__(self):
        pass  # skip the real `import keyring` check

    def get_secret(self, name):
        return KeyringCredentialStore.get_secret(self, name)


def _patch_keyring(monkeypatch, raising=True):
    import keyring

    def boom(*_a, **_k):
        raise RuntimeError("Keychain error -50")

    if raising:
        monkeypatch.setattr(keyring, "get_password", boom)


def test_get_secret_raises_clean_credential_error(monkeypatch):
    _patch_keyring(monkeypatch)
    with pytest.raises(CredentialError):
        BoomKeyring().get_secret(NCBI_API_KEY)


def test_resolve_secret_swallows_store_error_to_none(monkeypatch):
    _patch_keyring(monkeypatch)
    # env escape hatch absent -> store errors -> None (search proceeds keyless)
    monkeypatch.delenv("CITEVAHTI_NCBI_API_KEY", raising=False)
    assert resolve_secret(NCBI_API_KEY, BoomKeyring()) is None


def test_env_escape_hatch_wins_even_when_store_broken(monkeypatch):
    _patch_keyring(monkeypatch)
    monkeypatch.setenv("CITEVAHTI_NCBI_API_KEY", "from-env")
    assert resolve_secret(NCBI_API_KEY, BoomKeyring()) == "from-env"


def test_secret_source_and_state_report_store_unavailable(monkeypatch):
    _patch_keyring(monkeypatch)
    monkeypatch.delenv("CITEVAHTI_NCBI_API_KEY", raising=False)
    assert secret_source(NCBI_API_KEY, BoomKeyring()) == "store_unavailable"
    assert secret_state(NCBI_API_KEY, BoomKeyring()) == "store_unavailable"
