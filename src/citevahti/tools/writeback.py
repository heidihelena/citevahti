"""The write-privileged surface (ADR-0010 PR 1o — the ONE file that can mutate an
external Zotero library).

Everything that leaves the ledger and touches the outside world lives here, per
ADR-0010 §5c ("a newly-added write capability shows up in a diff a reviewer is
watching"), strengthening the ADR-0001 posture:

- **Guarded writes** (``note_add`` … ``assessment_tag_mirror``): preview by default
  (``dry_run=True``); a confirmed write REQUIRES a ``confirm_token`` from a prior
  preview. The preview/confirm/undo invariants are enforced in the ``writeback``
  service layer — these are thin wrappers that cannot bypass it.
- **Decision-gated transactions** (``commit_decision`` + undo/list/get): the §6 chain —
  only a recorded human decision can be committed, never a one-call write, and a
  committed transaction is undoable (deletes only the items it created).
- **Connect flow** (``connect_zotero``, ``zotero_oauth_start/finish``,
  ``zotero_new_key_url``): keys are validated, stored in the OS keychain, and never
  written to config or echoed back; the OAuth token secret never reaches the browser.

The agent-facing exposure of these verbs stays constrained by ``agent/policy.py``
(commit_write is the ONE destructive open-world tool) — nothing here widens it.

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ..schemas.common import LibrarySelector
from ._common import _open_store


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


# ---- Zotero connect (key paste + OAuth) -----------------------------------
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
