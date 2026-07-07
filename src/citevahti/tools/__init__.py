"""Pinned tool signatures (Patch 7 corrections folded in).

This module fixes the tool *interface* for sign-off. Only step-1 capabilities
exist; every later-step behavior raises ``NotImplementedError`` tagged with its
build-order step so the surface is stable but nothing is built ahead of approval.

The dual-rating guard ORDER is demonstrated for ``rating_run_ai``: the model pin
and task authorization are enforced (real validators) before any AI behavior
would run. AI values are advisory and never decide.
"""

from __future__ import annotations

from typing import Optional

from ..schemas.common import LibrarySelector

# Read-only groups split out (ADR-0010 PR 1a/1b); re-exported so the public
# citevahti.tools.<name> surface is unchanged. Shared factory helpers live in ._common
# (imported here so the ~60 in-facade callers, and the staying stateful functions, resolve
# them) — the neutral module the group files depend on without a cycle back to the facade.
from ._common import _intake_service, _open_store, _pubmed_provider  # noqa: F401
from .settings import (  # noqa: F401
    ai_config_get,
    ai_config_set,
    ai_local_models,
    bib_sync,
    getting_started,
    onboard,
)
from .exports import (  # noqa: F401
    agreement_report,
    cite_export,
    cite_export_manuscript,
    evidence_export,
    export_report_docx,
    export_review_packet,
)
from .warehouse import (  # noqa: F401
    aggregate_ratings,
    atlas_contribution_preview,
    atlas_revoke,
    prisma_ledger,
    warehouse_configure,
    warehouse_emit,
    warehouse_export,
    warehouse_purge,
    warehouse_status,
)
from .corpus import (  # noqa: F401
    corpus_diff,
    map_bootstrap,
    snapshot,
    surveillance_refresh,
)
from .intake import (  # noqa: F401
    backfill_candidate_dois,
    import_results,
    literature_search,
    recheck_library,
    retraction_scan,
    scan_licenses,
    scan_retractions,
)
from .lexical import (  # noqa: F401
    claim_check,
    claim_lexical_check,
    extract,
)
from .support import (  # noqa: F401
    decide,
    get_support_rating,
    list_decisions,
    support_adjudicate,
    support_commit_human,
    support_compare,
    support_panel,
    support_run_ai,
    support_start,
)
from .rating import (  # noqa: F401
    assess,
    rating_adjudicate,
    rating_commit_human,
    rating_compare,
    rating_run_ai,
    rating_start,
)
from .claims import (  # noqa: F401
    accept_revision,
    add_claim,
    claim_bond_status,
    claim_mark_untestable,
    link_candidates,
    list_candidates,
    list_claims,
    propose_revision,
    reject_revision,
    unlink_candidate,
)
from .manuscript import (  # noqa: F401
    chat,
    check_paragraph,
    claim_tests_prompt,
    import_manuscript_docx,
    run_manuscript_tests,
    topic_screen_prompt,
)
from .reports import (  # noqa: F401
    claim_report,
    draft_context,
    evidence_map,
    methods_statement,
    model_advisor,
    triage,
)
from .search import (  # noqa: F401
    check_update,
    openalex_search,
    resolve_dois,
    resolve_dois_by_title,
    semanticscholar_search,
)
from .zotero_read import (  # noqa: F401
    cite,
    pandoc_status,
    zot_attachments,
    zot_collections,
    zot_item,
    zot_search,
    zotero_evidence,
    zotero_locate,
)


# ---- step 7: dual-rating engine + assess + retraction + prisma ----------
# ---- step 9: guarded write-back -----------------------------------------
def _writeback(root, *, service=None, dedupe_index=None, tag_reader=None):
    if service is not None:
        return service
    from ..writeback import WritebackService, make_backend
    store = _open_store(root)
    cfg = store.load_config()
    return WritebackService(store, make_backend(cfg), dedupe_index=dedupe_index,
                            tag_reader=tag_reader, confirm_required=cfg.writeback.confirm_required)


def note_add(target, title: str, markdown: str, library: LibrarySelector = "personal",
             dry_run: bool = True, confirm_token: Optional[str] = None, *,
             root: Optional[str] = None, service=None):
    return _writeback(root, service=service).note_add(
        target, title, markdown, library=library, dry_run=dry_run, confirm_token=confirm_token)


def annotation_add(target_attachment, page: str, text: str, comment: Optional[str] = None,
                   color: Optional[str] = None, library: LibrarySelector = "personal",
                   dry_run: bool = True, confirm_token: Optional[str] = None, *,
                   root: Optional[str] = None, service=None):
    return _writeback(root, service=service).annotation_add(
        target_attachment, page, text, comment=comment, color=color, library=library,
        dry_run=dry_run, confirm_token=confirm_token)


def item_add(metadata: dict, library: LibrarySelector = "personal",
             collection_key: Optional[str] = None, dedupe: bool = True, dry_run: bool = True,
             confirm_token: Optional[str] = None, *, root: Optional[str] = None,
             service=None, dedupe_index=None):
    return _writeback(root, service=service, dedupe_index=dedupe_index).item_add(
        metadata, library=library, collection_key=collection_key, dedupe=dedupe,
        dry_run=dry_run, confirm_token=confirm_token)


def tag_add(targets, tags: list[str], library: LibrarySelector = "personal",
            dry_run: bool = True, confirm_token: Optional[str] = None, *,
            root: Optional[str] = None, service=None):
    return _writeback(root, service=service).tag_add(
        targets, tags, library=library, dry_run=dry_run, confirm_token=confirm_token)


def tag_remove(targets, tags: list[str], library: LibrarySelector = "personal",
               dry_run: bool = True, confirm_token: Optional[str] = None, *,
               root: Optional[str] = None, service=None):
    return _writeback(root, service=service).tag_remove(
        targets, tags, library=library, dry_run=dry_run, confirm_token=confirm_token)


def collection_add_item(collection_key: str, items, library: LibrarySelector = "personal",
                        dry_run: bool = True, confirm_token: Optional[str] = None, *,
                        root: Optional[str] = None, service=None):
    return _writeback(root, service=service).collection_add_item(
        collection_key, items, library=library, dry_run=dry_run, confirm_token=confirm_token)


def intake_push(intake_batch_id: str, record_ids: Optional[list[str]] = None,
                collection_key: Optional[str] = None, library: LibrarySelector = "personal",
                dry_run: bool = True, confirm_token: Optional[str] = None,
                allow_review_required: bool = False, *,
                root: Optional[str] = None, service=None, dedupe_index=None):
    return _writeback(root, service=service, dedupe_index=dedupe_index).intake_push(
        intake_batch_id, record_ids=record_ids, collection_key=collection_key, library=library,
        dry_run=dry_run, confirm_token=confirm_token, allow_review_required=allow_review_required)


def assessment_tag_mirror(rating_id: Optional[str] = None,
                          assessment_attachment_id: Optional[str] = None, dry_run: bool = True,
                          confirm_token: Optional[str] = None, *, root: Optional[str] = None,
                          service=None, tag_reader=None):
    return _writeback(root, service=service, tag_reader=tag_reader).assessment_tag_mirror(
        rating_id=rating_id, assessment_attachment_id=assessment_attachment_id, dry_run=dry_run,
        confirm_token=confirm_token)


# ---- onboarding (secure credential capture) -----------------------------
# ---- ADR-0001 step 1: claims --------------------------------------------
def zotero_new_key_url(name: str = "CiteVahti", *, groups: str = "none") -> str:
    """The pre-filled Zotero new-key page (one click → Save → copy).

    ``groups`` (none|read|write) pre-selects shared/group-library access.
    """
    from ..zotero import new_key_url
    return new_key_url(name, groups=groups)


def connect_zotero(api_key: str, *, require_write: bool = True, root: Optional[str] = None,
                   http=None, credential_store=None):
    """Validate a pasted Zotero key, learn the userID, store it, enable guarded write.

    The key is stored in the OS keychain and never written to config or echoed back.
    """
    from ..zotero import ZoteroConnectService
    return ZoteroConnectService(_open_store(root), http=http,
                                credential_store=credential_store).connect(
        api_key, require_write=require_write)


def zotero_oauth_start(callback: str, *, root: Optional[str] = None, http=None) -> dict:
    """Begin the Zotero OAuth 1.0a handshake; return the URL the user authorizes.

    Needs a registered CiteVahti OAuth app (client key/secret in the env). The
    returned ``oauth_token_secret`` is held by the caller (the loopback panel) only
    until the callback completes — never sent to the browser."""
    from ..zotero import ZoteroOAuth, ZoteroOAuthError, load_client_credentials
    ck, cs = load_client_credentials()
    if not (ck and cs):
        raise ZoteroOAuthError(
            "not_configured",
            "Zotero OAuth app is not configured. Register CiteVahti at "
            "https://www.zotero.org/oauth/apps and set CITEVAHTI_ZOTERO_OAUTH_CLIENT_KEY "
            "and CITEVAHTI_ZOTERO_OAUTH_CLIENT_SECRET — or paste an API key instead.")
    oa = ZoteroOAuth(ck, cs, http=http)
    token, token_secret = oa.request_token(callback)
    return {"oauth_token": token, "oauth_token_secret": token_secret,
            "authorize_url": oa.authorize_url(token)}


def zotero_oauth_finish(oauth_token: str, token_secret: str, verifier: str, *,
                        root: Optional[str] = None, http=None) -> dict:
    """Exchange the verified token for the API key and store it (write enabled).

    Reuses ``connect_zotero``'s storage path, so an OAuth connect and a pasted key
    converge on the same validated, keyring-stored, write-enabled state."""
    from ..zotero import ZoteroOAuth, load_client_credentials
    ck, cs = load_client_credentials()
    if not ck or not cs:
        raise ValueError("Zotero OAuth is not configured (set the client key/secret env vars); "
                         "use the paste-a-key flow instead.")
    oa = ZoteroOAuth(ck, cs, http=http)
    result = oa.access_token(oauth_token, token_secret, verifier)
    connect_zotero(result["api_key"], root=root)      # validate + keyring-store + enable write
    return {"connected": True, "user_id": result["user_id"]}


# ---- ADR-0001 step 3: claim-support dual rating --------------------------
# ---- ADR-0001 step 5: decision-gated write transactions + undo -----------
def _transaction_service(root):
    from ..writeback import TransactionService, make_backend
    store = _open_store(root)
    return TransactionService(store, make_backend(store.load_config()))


def commit_decision(decision_id: str, *, collection_key: Optional[str] = None,
                    library: Optional[str] = None, dry_run: bool = True,
                    confirm_token: Optional[str] = None, allow_unverified_dedupe: bool = False,
                    root: Optional[str] = None):
    """Validated, decision-gated Zotero write (preview by default). Enforces the §6 chain.

    A confirmed write (``dry_run=False``) REQUIRES ``confirm_token`` from a prior
    preview — agent-facing callers cannot one-call write without that approval step.

    ``library`` is a writeback selector string ('personal' | 'all' | 'group:<id>').
    When omitted it falls back to the configured default (``Config.default_library``),
    so a group-library user writes to their group without passing it every time.
    """
    if library is None:
        library = _open_store(root).load_config().resolved_default_library()
    return _transaction_service(root).commit_for_decision(
        decision_id, collection_key=collection_key, library=library, dry_run=dry_run,
        confirm_token=confirm_token, allow_unverified_dedupe=allow_unverified_dedupe)


def undo_transaction(transaction_id: str, *, root: Optional[str] = None):
    """Undo a committed write transaction (deletes only the items it created)."""
    return _transaction_service(root).undo(transaction_id)


def list_transactions(*, root: Optional[str] = None):
    """List write transactions (read-only)."""
    return _transaction_service(root).list()


def get_transaction(transaction_id: str, *, root: Optional[str] = None):
    """Show a write transaction (read-only)."""
    return _transaction_service(root).get(transaction_id)
