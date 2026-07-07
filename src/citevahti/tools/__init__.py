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

from ..probe.client import HttpxClient
from ..schemas.bibsync import ExportFormat
from ..schemas.common import LibrarySelector
from ..schemas.config import Endpoints

# Read-only groups split out (ADR-0010 PR 1a/1b); re-exported so the public
# citevahti.tools.<name> surface is unchanged. Shared factory helpers live in ._common
# (imported here so the ~60 in-facade callers, and the staying stateful functions, resolve
# them) — the neutral module the group files depend on without a cycle back to the facade.
from ._common import _intake_service, _open_store, _pubmed_provider  # noqa: F401
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


# ---- step 3: bib_sync + evidence_map ------------------------------------
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


# ---- step 7: dual-rating engine + assess + retraction + prisma ----------
def getting_started(*, root: Optional[str] = None):
    """Where the project is and the single next thing to do — the state-aware first-run
    / resume guide (``workflow.project_status``). Speaks to every state, including the
    empty ones an uninitialized ledger is in ("create the ledger", "paste a paragraph"),
    which the risk-first ``triage`` cannot. Read-only; derives "what's next" fresh each
    call, so nothing is stored."""
    from .. import workflow
    return workflow.project_status(root or ".")


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


# ---- citation-integrity report (the 4-state "test results") --------------
# ---- the manuscript "unit test" suite ---------------------------------------
# CiteVahti's core metaphor: each claim is a test case. A claim PASSES when it is
# backed by accepted, supporting evidence whose citation is identifiable (and,
# online, real + not retracted); FAILS when the citation does not support it, is
# retracted, or can't be identified; SKIPS when not yet reviewed or out of scope.
_ACCEPTED_DECISIONS = ("accept", "accepted_with_caution")


def _evaluate_claim_tests(row, online: bool) -> dict:
    checks: list[dict] = []

    def add(name, status, detail=""):
        checks.append({"name": name, "status": status, "detail": detail})

    def result(status):
        return {"claim_id": row.claim_id, "claim_text": row.claim_text,
                "state": row.state, "code": row.code.strip(),
                "manuscript_location": row.manuscript_location,
                "status": status, "checks": checks}

    # FAIL (loudly): a decision was edited outside CiteVahti — the ledger state can't be
    # trusted. Never a silent skip; the citation integrity of this claim is unknown.
    if getattr(row, "inconsistent", False):
        add("ledger_integrity", "fail",
            "ledger state is inconsistent with the audit trail (edited outside CiteVahti): "
            + (row.inconsistency or "decision disagrees with its rating"))
        return result("fail")
    # SKIP: explicitly out of indexed scope (book/grey lit) — not a failure.
    if row.state == "untestable":
        add("in_scope", "skip", row.untestable_reason or "cited source is out of indexed-literature scope")
        return result("skip")
    # SKIP: not yet reviewed (no evidence linked, or linked but not rated/decided).
    if row.state == "needs_support":
        detail = "no reference linked yet" if row.candidate_count == 0 else "evidence linked but not yet rated/decided"
        add("reviewed", "skip", detail)
        return result("skip")

    # decided states: accepted / review_needed / decision_recorded
    add("has_reference", "pass" if row.candidate_count >= 1 else "fail",
        "" if row.candidate_count >= 1 else "no reference linked")
    add("reviewed", "pass")

    if row.state == "review_needed":
        add("supported", "fail", "rater discordance or a needs-second-review verdict is unresolved")
        return result("fail")
    if row.state == "decision_recorded":
        add("supported", "fail", "no candidate was accepted as supporting this claim")
        return result("fail")

    # state == "accepted": the claim is supported — now test the citation itself.
    add("supported", "pass")
    accepted = [e for e in row.evidence if e.final_decision in _ACCEPTED_DECISIONS]
    operative = accepted or row.evidence
    identified = [e for e in operative if (e.doi or e.pmid)]
    add("citation_identified", "pass" if identified else "fail",
        "" if identified else "the supporting reference has no DOI or PMID")
    if online:
        retracted = [e for e in operative if e.retracted]
        add("not_retracted", "fail" if retracted else "pass",
            f"{len(retracted)} supporting reference(s) flagged retracted" if retracted else "")
        add("citation_real", "pass" if identified else "fail",
            "" if identified else "could not resolve a real DOI/PMID for the reference")

    return result("fail" if any(c["status"] == "fail" for c in checks) else "pass")


def run_manuscript_tests(*, root: Optional[str] = None, online: bool = False,
                         claim_ids: Optional[list] = None, http=None) -> dict:
    """Run the manuscript 'unit test' suite over the ledger's claims.

    Offline checks (instant, deterministic): the claim has a linked reference, was
    reviewed, the verdict supports it, and the supporting citation carries a DOI/PMID.
    With ``online=True`` it first refreshes retraction flags and backfills/validates
    identifiers (network), then also tests that the citation is real and not retracted.

    Returns a JSON-serialisable suite result so the CLI and the panel share one engine.
    """
    online_actions: dict = {}
    if online:
        try:
            online_actions["retractions"] = scan_retractions(root=root, http=http)
        except Exception as e:  # noqa: BLE001 — a flaky network check must not crash the suite
            online_actions["retractions_error"] = str(e)
        try:
            online_actions["dois"] = backfill_candidate_dois(root=root, http=http)
        except Exception as e:  # noqa: BLE001
            online_actions["dois_error"] = str(e)

    rep = claim_report(claim_ids=claim_ids, root=root)
    claims = [_evaluate_claim_tests(r, online) for r in rep.rows]
    counts = {s: sum(1 for c in claims if c["status"] == s) for s in ("pass", "fail", "skip")}
    # Surface online-check failures explicitly: a swallowed retraction-scan / DOI
    # backfill error means the citation_real / not_retracted checks ran against stale
    # data, so a "pass" there is NOT trustworthy. Callers MUST show online_errors.
    online_errors = [v for k, v in online_actions.items() if k.endswith("_error")]
    return {"total": len(claims), "passed": counts["pass"], "failed": counts["fail"],
            "skipped": counts["skip"], "online": online, "claims": claims,
            "online_actions": online_actions or None, "online_errors": online_errors,
            "generated_at": rep.generated_at}


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
