"""Onboarding, AI-connection settings, first-run guide, bib-sync (ADR-0010 PR 1n).

Configuration-side tools: guided onboarding (non-secret identifiers -> config, secret
keys -> OS keyring/env; never written to config or echoed back), the panel's AI second
opinion settings (mode/endpoint/model; the secret's VALUE is never returned, only whether
one is present), the state-aware ``getting_started`` guide, and the multi-file citation
``bib_sync``. Config/ledger-side only; the Zotero key/OAuth *connect* flow is the write
surface and lives in ``tools/writeback.py``.

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ..probe.client import HttpxClient
from ..schemas.bibsync import ExportFormat
from ..schemas.common import LibrarySelector
from ..schemas.config import Endpoints
from ._common import _open_store


def bib_sync(targets: dict, output_dir: Optional[str] = None,
             export_format: ExportFormat = "bibtex", include_cited_only: bool = True,
             make_master: bool = True, fail_on_orphans: bool = False,
             library: LibrarySelector = "personal", *,
             endpoints: Optional[Endpoints] = None, provider=None, root: Optional[str] = None):
    """Multi-file citation sync. ``targets={"paths": [...]}``. Returns a BibSyncReport.

    Resolves citekeys by exact match through Better BibTeX (never inventing keys)
    and degrades honestly when BBT is absent.
    """
    from ..bibsync import BbtBibProvider, BibSyncService
    from ..state import CiteVahtiStore

    if provider is None:
        provider = BbtBibProvider(HttpxClient(), endpoints)
    store = None
    if root is not None:
        candidate = CiteVahtiStore(root)
        if candidate.exists():
            store = candidate
    paths = targets.get("paths", []) if isinstance(targets, dict) else list(targets)
    return BibSyncService(provider, store).run(
        paths, output_dir=output_dir, export_format=export_format,
        include_cited_only=include_cited_only, make_master=make_master,
        fail_on_orphans=fail_on_orphans, library=library)


def getting_started(*, root: Optional[str] = None):
    """Where the project is and the single next thing to do — the state-aware first-run
    / resume guide (``workflow.project_status``). Speaks to every state, including the
    empty ones an uninitialized ledger is in ("create the ledger", "paste a paragraph"),
    which the risk-first ``triage`` cannot. Read-only; derives "what's next" fresh each
    call, so nothing is stored."""
    from .. import workflow
    return workflow.project_status(root or ".")


def onboard(*, root: Optional[str] = None, ncbi_email: Optional[str] = None,
            zotero_user_id: Optional[str] = None, zotero_library_id: Optional[str] = None,
            zotero_library_type: str = "user", default_collection_key: Optional[str] = None,
            zotero_write_key: Optional[str] = None, ncbi_api_key: Optional[str] = None,
            fullvahti_token: Optional[str] = None,
            secrets_backend: str = "system_keyring", validate: bool = True,
            credential_store=None, validators="auto"):
    """Capture non-secret identifiers (config) and secret keys (OS keyring/env).

    Secrets are held in memory, validated where possible, then stored; they are
    never written to config or echoed back.
    """
    from ..onboarding import LiveValidators, OnboardingService

    store = _open_store(root)
    vals = None
    if validate and validators == "auto":
        vals = LiveValidators(HttpxClient())
    elif validators not in (None, "auto"):
        vals = validators
    return OnboardingService(store, credential_store=credential_store, validators=vals).onboard(
        ncbi_email=ncbi_email, zotero_user_id=zotero_user_id, zotero_library_id=zotero_library_id,
        zotero_library_type=zotero_library_type, default_collection_key=default_collection_key,
        zotero_write_key=zotero_write_key, ncbi_api_key=ncbi_api_key,
        fullvahti_token=fullvahti_token, secrets_backend=secrets_backend, validate=validate)


# ---- AI assistant settings (panel) -----------------------------------------
# How the (optional) AI second opinion is sourced. Most users drive CiteVahti
# through an assistant over MCP — it submits a blinded rating with no key, the
# subscription pays. These settings only govern CiteVahti's OWN call (local /
# external), used by the standalone / high-volume screener. The secret value is
# never returned — only whether one is present.
_AI_MODES = ("off", "local", "api")
_LOCAL_DEFAULT_ENDPOINT = "http://localhost:11434/v1/chat/completions"


def ai_config_get(*, root: Optional[str] = None) -> dict:
    from ..credentials import AI_API_KEY, CredentialError, get_credential_store, resolve_secret
    cfg = _open_store(root).load_config()
    conn, prov = cfg.ai_connection, cfg.ai_provenance
    try:
        store = get_credential_store(cfg.secrets_backend)
    except CredentialError:
        store = None  # keyring extra absent — env escape hatch still resolves
    return {
        "mode": conn.mode,
        "endpoint": conn.endpoint,
        "request_timeout_s": conn.request_timeout_s,
        "provider": prov.provider,
        "model_id": prov.model_id,
        "model_snapshot": prov.model_snapshot,
        "model_pinned": prov.is_model_pinned(),
        "api_key_present": bool(resolve_secret(AI_API_KEY, store)),  # never the value
    }


def ai_config_set(*, mode: Optional[str] = None, endpoint: Optional[str] = None,
                  provider: Optional[str] = None, model_id: Optional[str] = None,
                  root: Optional[str] = None) -> dict:
    from ..rating import ollama_model_snapshot
    if mode is not None and mode not in _AI_MODES:
        raise ValueError(f"mode must be one of {_AI_MODES}")
    s = _open_store(root)
    cfg = s.load_config()
    conn, prov = cfg.ai_connection, cfg.ai_provenance
    if mode is not None:
        conn.mode = mode
    if endpoint is not None:
        conn.endpoint = endpoint or None
    if provider is not None:
        prov.provider = provider
    if model_id is not None:
        prov.model_id = model_id
    # local mode: auto-pin the Ollama digest as the snapshot so the local model is
    # auditable like a cloud one (falls back to the model tag if Ollama is down).
    if conn.mode == "local" and prov.model_id:
        ep = conn.endpoint or _LOCAL_DEFAULT_ENDPOINT
        try:
            digest = ollama_model_snapshot(ep, prov.model_id)
        except Exception:  # noqa: BLE001
            digest = None
        prov.model_snapshot = digest or f"ollama:{prov.model_id}"
    s.save_config(cfg)
    return ai_config_get(root=root)


def ai_local_models(*, root: Optional[str] = None) -> dict:
    """Installed local (Ollama) models + a suggested one (Qwen-first). Empty when
    Ollama isn't running — the panel offers the default name and stays usable."""
    from ..rating import list_ollama_models, suggest_local_model
    cfg = _open_store(root).load_config()
    ep = cfg.ai_connection.endpoint or _LOCAL_DEFAULT_ENDPOINT
    models = list_ollama_models(ep)
    return {"models": models, "suggested": suggest_local_model(models)}
