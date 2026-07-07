"""Shared tool factory helpers (ADR-0010 PR 1b — the neutral module).

Store and provider constructors that many tool groups need in common. They live here,
not in ``tools/__init__.py``, so a group module can depend on them without importing back
into the package facade (which would be a cycle). Nothing in the wider codebase imports
these directly — ``citevahti.tools`` re-imports them so its ~60 in-facade callers are
unchanged, and the split group modules import them from ``._common``.

Dependency direction (ADR-0010 §3): ``_common`` imports nothing from the ``tools`` package;
group modules and the facade import from it. No lazy service imports are hoisted — each
helper keeps its in-body imports so importing this module stays cheap and cycle-free.
"""

from __future__ import annotations

from typing import Optional

from ..probe.client import HttpxClient


def _open_store(root: Optional[str]):
    import os

    from ..state import CiteVahtiStore
    store = CiteVahtiStore(root or os.getcwd())
    if not store.exists():
        raise ValueError(f"{store.dir} is not initialized; run `citevahti init` first")
    return store


def _intake_service(root: Optional[str], library, endpoints, provider, library_index):
    import os

    from ..intake import IntakeService, ZoteroLibraryIndex
    from ..pubmed import PubMedProvider
    from ..state import CiteVahtiStore
    from ..zotero import ZoteroService

    from ..credentials import NCBI_API_KEY, get_credential_store, resolve_secret

    store = CiteVahtiStore(root or os.getcwd())
    if not store.exists():
        raise ValueError(f"{store.dir} is not initialized; run `citevahti init` first")
    http = HttpxClient()
    if provider is None:
        cfg = store.load_config()
        # email: env override -> onboarded config value
        email = os.environ.get(cfg.pubmed.email_env) or cfg.pubmed.contact_email
        # NCBI key: env escape hatch -> OS keyring (never from config)
        try:
            cred_store = get_credential_store(getattr(cfg, "secrets_backend", "system_keyring"))
        except Exception:  # noqa: BLE001
            cred_store = None
        api_key = resolve_secret(NCBI_API_KEY, cred_store) or os.environ.get(cfg.pubmed.api_key_env)
        provider = PubMedProvider(http, email, api_key)
    if library_index is None:
        library_index = ZoteroLibraryIndex(ZoteroService(http, endpoints), library)
    return IntakeService(store, provider=provider, library_index=library_index)


def _pubmed_provider(root: Optional[str], http=None):
    """Build a PubMedProvider with the onboarded NCBI email/key (same resolution the
    intake path uses) — used for DOI resolution outside a full literature_search."""
    import os

    from ..credentials import NCBI_API_KEY, get_credential_store, resolve_secret
    from ..pubmed import PubMedProvider

    cfg = _open_store(root).load_config()
    email = os.environ.get(cfg.pubmed.email_env) or cfg.pubmed.contact_email
    try:
        cred_store = get_credential_store(getattr(cfg, "secrets_backend", "system_keyring"))
    except Exception:  # noqa: BLE001
        cred_store = None
    api_key = resolve_secret(NCBI_API_KEY, cred_store) or os.environ.get(cfg.pubmed.api_key_env)
    return PubMedProvider(http or HttpxClient(), email, api_key)
