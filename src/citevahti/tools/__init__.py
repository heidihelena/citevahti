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
from ..schemas.common import ItemRef, LibrarySelector
from ..schemas.config import Endpoints

# Read-only groups split out (ADR-0010 PR 1a/1b); re-exported so the public
# citevahti.tools.<name> surface is unchanged. Shared factory helpers live in ._common
# (imported here so the ~60 in-facade callers, and the staying stateful functions, resolve
# them) — the neutral module the group files depend on without a cycle back to the facade.
from ._common import _intake_service, _open_store, _pubmed_provider  # noqa: F401
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


def _todo(step: int, tool: str):
    raise NotImplementedError(f"{tool}: scheduled for build order step {step}; not yet approved")


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


# ---- step 4: extract + claim_check --------------------------------------
def _text_source(endpoints: Optional[Endpoints]):
    from ..bbt.client import BbtClient
    from ..retrieval import ZoteroApiTextSource
    from ..zotero import ZoteroService

    http = HttpxClient()
    return ZoteroApiTextSource(ZoteroService(http, endpoints), BbtClient(http, endpoints))


def extract(subject: ItemRef, fields: Optional[list[str]] = None, mode: str = "assistive",
            require_passage: bool = False, library: LibrarySelector = "personal", *,
            source=None, endpoints: Optional[Endpoints] = None):
    """Assistive, deterministic field extraction. Returns an ExtractResult.
    Never guesses; never writes to the evidence map."""
    from ..extract import ExtractService

    src = source or _text_source(endpoints)
    return ExtractService(src).extract(subject, fields, mode=mode,
                                       require_passage=require_passage, library=library)


def claim_check(claim_text: str, citekeys: list[str], context: Optional[str] = None,
                require_page: bool = False, library: LibrarySelector = "personal", *,
                source=None, endpoints: Optional[Endpoints] = None):
    """Deterministic lexical claim support. Returns a ClaimCheckResult.
    Never asserts truth; never invents keys; exact citekey resolution only."""
    from ..claimcheck import ClaimCheckService

    src = source or _text_source(endpoints)
    return ClaimCheckService(src).check(claim_text, citekeys, context=context,
                                        require_page=require_page, library=library)


# ---- step 5: literature_search + import_results (PubMed) ----------------
def literature_search(query: str, question_id: Optional[str] = None, max_results: int = 20,
                      date_range: Optional[dict] = None, include_abstracts: bool = False,
                      library: LibrarySelector = "personal", *, root: Optional[str] = None,
                      endpoints: Optional[Endpoints] = None, provider=None, library_index=None):
    """Run a USER-SUPPLIED PubMed query and stage results (pre-decision).
    Never designs the query, never decides inclusion, never imports into Zotero."""
    svc = _intake_service(root, library, endpoints, provider, library_index)
    return svc.literature_search(query, question_id=question_id, max_results=max_results,
                                 date_range=date_range, include_abstracts=include_abstracts,
                                 library=library)


def _iter_candidate_collections(store, root):
    """Yield each claim's candidate collection (skipping claims with none)."""
    for row in claim_report(root=root).rows:
        try:
            yield store.load_candidates(row.claim_id)
        except Exception:  # noqa: BLE001 — a claim with no linked candidates
            continue


def backfill_candidate_dois(*, root: Optional[str] = None, http=None, include_title: bool = True) -> dict:
    """Resolve DOIs for EXISTING candidates missing one. PMID→DOI (NCBI,
    authoritative) for candidates with a PMID; CrossRef title→DOI (strict) for those
    with no identifier at all. The link-time resolver only fires on new links — this
    cleans up ones linked earlier."""
    store = _open_store(root)
    cols = list(_iter_candidate_collections(store, root))
    pmids = {c.pmid for cc in cols for c in cc.candidates if c.pmid and not c.doi}
    titles = {c.title for cc in cols for c in cc.candidates
              if not c.pmid and not c.doi and c.title} if include_title else set()
    by_pmid = resolve_dois(sorted(pmids), root=root, http=http) if pmids else {}
    by_title = resolve_dois_by_title(sorted(titles), root=root, http=http) if titles else {}
    if not by_pmid and not by_title:
        return {"resolved": 0, "by_pmid": 0, "by_title": 0}
    n_pmid = n_title = 0
    for cc in cols:
        changed = False
        new = []
        for c in cc.candidates:
            if not c.doi and c.pmid in by_pmid:
                new.append(c.model_copy(update={"doi": by_pmid[c.pmid]}))
                changed, n_pmid = True, n_pmid + 1
            elif not c.doi and not c.pmid and c.title in by_title:
                new.append(c.model_copy(update={"doi": by_title[c.title]}))
                changed, n_title = True, n_title + 1
            else:
                new.append(c)
        if changed:
            cc.candidates = new
            store.save_candidates(cc)
    return {"resolved": n_pmid + n_title, "by_pmid": n_pmid, "by_title": n_title}


def recheck_library(library="personal", *, root: Optional[str] = None,
                    endpoints: Optional[Endpoints] = None, index=None, zotero=None) -> dict:
    """Re-run library dedupe for existing candidates and flag those now in Zotero.

    ``already_in_zotero`` is set at link time; if the library wasn't connected then,
    candidates stay unflagged. This re-checks each against the live library."""
    store = _open_store(root)
    if index is None:
        from ..intake.dedupe import ZoteroLibraryIndex
        from ..zotero import ZoteroService
        index = ZoteroLibraryIndex(zotero or ZoteroService(HttpxClient(), endpoints), library)
    flagged = checked = 0
    for cc in _iter_candidate_collections(store, root):
        changed = False
        new = []
        for c in cc.candidates:
            checked += 1
            present = index.contains(c.pmid, c.doi)
            if present is True and not c.already_in_zotero:
                new.append(c.model_copy(update={"already_in_zotero": True,
                                                "dedupe_status": "already_in_library"}))
                changed = True
                flagged += 1
            else:
                new.append(c)
        if changed:
            cc.candidates = new
            store.save_candidates(cc)
    return {"flagged": flagged, "checked": checked}


def scan_retractions(*, root: Optional[str] = None, http=None, client=None) -> dict:
    """Flag candidates whose DOI/PMID is retracted (OpenAlex ``is_retracted``).

    Citation-integrity flagship: a student citing a retracted paper is exactly what
    this catches. Only flags on a definite True; unknown/offline leaves it unset."""
    store = _open_store(root)
    if client is None:
        from ..openalex import OpenAlexClient
        try:
            mailto = store.load_config().pubmed.contact_email
        except Exception:  # noqa: BLE001
            mailto = None
        client = OpenAlexClient(http=http, mailto=mailto)
    flagged = checked = 0
    for cc in _iter_candidate_collections(store, root):
        changed = False
        new = []
        for c in cc.candidates:
            if c.doi or c.pmid:
                checked += 1
                if client.is_retracted(doi=c.doi, pmid=c.pmid) is True and not c.retracted:
                    new.append(c.model_copy(update={"retracted": True}))
                    changed, flagged = True, flagged + 1
                    continue
            new.append(c)
        if changed:
            cc.candidates = new
            store.save_candidates(cc)
    # Logged even when nothing was flagged: the report cites this timestamp as
    # "retractions last checked", so a clean scan must be distinguishable from
    # never having scanned.
    store.audit.append("retraction.scan",
                       {"checked": checked, "flagged": flagged,
                        "source": "openalex.is_retracted"})
    return {"flagged": flagged, "checked": checked}


def scan_licenses(*, root: Optional[str] = None, http=None, client=None) -> dict:
    """Fill each candidate's reuse rights (``oa_status``/``license``) from OpenAlex.

    REPORTS, never DECIDES: it records what the source's licence is so a human (or a
    downstream tool like a content hub) can judge reuse — CiteVahti never says a source
    is OK to republish. Unknown/offline leaves the fields unset (never a false 'closed')."""
    store = _open_store(root)
    if client is None:
        from ..openalex import OpenAlexClient
        try:
            mailto = store.load_config().pubmed.contact_email
        except Exception:  # noqa: BLE001
            mailto = None
        client = OpenAlexClient(http=http, mailto=mailto)
    filled = checked = 0
    for cc in _iter_candidate_collections(store, root):
        changed = False
        new = []
        for c in cc.candidates:
            if c.doi or c.pmid:
                checked += 1
                rights = client.licensing(doi=c.doi, pmid=c.pmid)
                if rights and (rights.get("oa_status") or rights.get("license")):
                    new.append(c.model_copy(update={
                        "oa_status": rights.get("oa_status"),
                        "license": rights.get("license")}))
                    changed, filled = True, filled + 1
                    continue
            new.append(c)
        if changed:
            cc.candidates = new
            store.save_candidates(cc)
    store.audit.append("license.scan",
                       {"checked": checked, "filled": filled,
                        "source": "openalex.open_access"})
    return {"filled": filled, "checked": checked}


def claim_lexical_check(claim_text: str, text: str) -> dict:
    """Deterministic lexical overlap between a claim and a passage (the candidate's
    abstract/full text). Reuses the same content-token logic as ``claim_check``.

    NEVER asserts truth — only whether the claim's key terms appear in the text. The
    panel shows it AFTER the human's blind rating so it can't bias it."""
    from ..retrieval.text import (content_tokens, coverage_score,
                                 polarity_conflict, polarity_cue, segment_sentences)
    claim_terms = content_tokens(claim_text or "")
    if not claim_terms or not (text or "").strip():
        return {"available": False}
    text_terms = content_tokens(text)
    cov = coverage_score(claim_text, text)
    # Direction guard (same rule as claim_check): a sentence can overlap the claim's
    # terms yet assert the OPPOSITE polarity ("did not reduce" vs "reduced"). Surface
    # it as an inspectable "may contradict" cue — never a verdict, never hidden.
    opposing = next((s for _a, _b, s in segment_sentences(text)
                     if polarity_conflict(claim_text, s)), None)
    cue = polarity_cue(claim_text, opposing) if opposing else None
    return {
        "available": True,
        "coverage": round(cov, 2),
        "status": "terms_present" if cov >= 0.5 else "terms_missing",
        "present": sorted(t for t in claim_terms if t in text_terms),
        "missing": sorted(t for t in claim_terms if t not in text_terms),
        "contradiction": opposing is not None,
        "polarity_cue": cue,
        "opposing_quote": opposing,
    }


def import_results(source: dict, format: str, question_id: Optional[str] = None,
                   source_label: Optional[str] = None, library: LibrarySelector = "personal", *,
                   root: Optional[str] = None, endpoints: Optional[Endpoints] = None,
                   library_index=None):
    """Manual fallback staging from RIS/CSV/BibTeX (pre-decision). No Zotero import."""
    # provider not needed for manual import
    svc = _intake_service(root, library, endpoints, provider="__manual__", library_index=library_index)
    return svc.import_results(source, format, question_id=question_id,
                              source_label=source_label, library=library)


# ---- step 6: snapshot / corpus_diff / surveillance / map_bootstrap -------
def _corpus_source(endpoints: Optional[Endpoints]):
    from ..bbt.client import BbtClient
    from ..corpus import ZoteroCorpusSource
    from ..probe.probe import run_probes
    from ..zotero import ZoteroService

    http = HttpxClient()
    cap = run_probes(http, endpoints)
    return ZoteroCorpusSource(ZoteroService(http, endpoints, cap), BbtClient(http, endpoints), cap)


def snapshot(label: Optional[str] = None, library: LibrarySelector = "personal",
             include_fulltext_hashes: bool = False, include_retraction_status: bool = False, *,
             root: Optional[str] = None, endpoints: Optional[Endpoints] = None, source=None):
    """Read-only hashed capture of corpus + evidence-map state."""
    from ..corpus import SnapshotService
    store = _open_store(root)
    return SnapshotService(store, source or _corpus_source(endpoints)).snapshot(
        label=label, library=library, include_fulltext_hashes=include_fulltext_hashes,
        include_retraction_status=include_retraction_status)


def corpus_diff(from_snapshot_id: str, to_snapshot_id: Optional[str] = None,
                compare_to_current: bool = False, mark_stale: bool = False,
                library: LibrarySelector = "personal", *, root: Optional[str] = None,
                endpoints: Optional[Endpoints] = None, source=None):
    """Compare snapshots (or snapshot vs current) and report/flag staleness."""
    from ..corpus import CorpusDiffService
    store = _open_store(root)
    src = source or (_corpus_source(endpoints) if compare_to_current else None)
    return CorpusDiffService(store, src).diff(
        from_snapshot_id, to_snapshot_id=to_snapshot_id, compare_to_current=compare_to_current,
        mark_stale=mark_stale, library=library)


def surveillance_refresh(query_id: str, max_results: int = 20, map_to: Optional[dict] = None,
                         library: LibrarySelector = "personal", *, root: Optional[str] = None,
                         endpoints: Optional[Endpoints] = None, provider=None, library_index=None):
    """Refresh a saved PubMed query from its own last-run date (never snapshot date)."""
    svc = _intake_service(root, library, endpoints, provider, library_index)
    return svc.surveillance_refresh(query_id, max_results=max_results, map_to=map_to, library=library)


def map_bootstrap(guideline_path: str, bibliography_path: Optional[str] = None,
                  library: LibrarySelector = "personal", dry_run: bool = True, *,
                  root: Optional[str] = None, endpoints: Optional[Endpoints] = None, resolver=None):
    """Minimal deterministic evidence-map seeding from a guideline file."""
    from ..bbt.client import BbtClient
    from ..bootstrap import MapBootstrapService
    from ..retrieval import ZoteroApiTextSource
    from ..zotero import ZoteroService

    store = _open_store(root)
    if resolver is None:
        http = HttpxClient()
        resolver = ZoteroApiTextSource(ZoteroService(http, endpoints), BbtClient(http, endpoints))
    return MapBootstrapService(store, resolver).bootstrap(
        guideline_path, bibliography_path=bibliography_path, library=library, dry_run=dry_run)


# ---- step 7: dual-rating engine + assess + retraction + prisma ----------
def retraction_scan(selection: Optional[dict] = None, library: LibrarySelector = "personal",
                    mark_stale: bool = False, *, root: Optional[str] = None, provider=None):
    """DOI/PMID retraction scan; never title-only; degrades honestly offline."""
    from ..retraction import FakeRetractionProvider, RetractionScanService
    store = _open_store(root)
    if provider is None:
        # No live retraction provider is configured in step 7 -> degrade honestly.
        provider = FakeRetractionProvider(available=False)
    return RetractionScanService(store, provider).scan(selection, library=library,
                                                       mark_stale=mark_stale)


def prisma_ledger(question_id: str, action: str, payload: Optional[dict] = None, *,
                  root: Optional[str] = None):
    """Human-only PRISMA flow accounting. AI votes are rating_id references only."""
    from ..prisma import PrismaLedgerService
    return PrismaLedgerService(_open_store(root)).prisma_ledger(question_id, action, payload)


# ---- step 8: evidence_export + agreement_report -------------------------
def aggregate_ratings(frame_id: str, actor_ids: Optional[list[str]] = None):
    """Refuses to aggregate across mismatched frame_version or scheme_id."""
    _todo(8, "aggregate_ratings")


def evidence_export(selection: Optional[dict] = None, formats: Optional[list[str]] = None,
                    include_provenance: bool = False, include_ai_values: bool = False,
                    output_dir: Optional[str] = None, *, root: Optional[str] = None):
    """Neutral CSV/Markdown/CSL-JSON evidence tables. Read-only; no judgments."""
    from ..export import EvidenceExportService
    return EvidenceExportService(_open_store(root)).export(
        selection=selection, formats=formats, include_provenance=include_provenance,
        include_ai_values=include_ai_values, output_dir=output_dir)


def agreement_report(filters: Optional[dict] = None, metrics: Optional[list[str]] = None,
                     output_formats: Optional[list[str]] = None, output_dir: Optional[str] = None,
                     *, root: Optional[str] = None):
    """Human-AI agreement metrics + method-transparency section. Read-only."""
    from ..export import AgreementReportService
    return AgreementReportService(_open_store(root)).report(
        filters=filters, metrics=metrics, output_formats=output_formats, output_dir=output_dir)


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
def warehouse_status(*, root: Optional[str] = None):
    """De-identified validation warehouse status (read-only)."""
    from ..warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).status()


def warehouse_emit(claim_id: str, candidate_id: str, *, root: Optional[str] = None):
    """Emit one de-identified validation record for a (claim, candidate). No-op if disabled."""
    from ..warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).emit_for_decision(claim_id, candidate_id)


def warehouse_export(output_path: Optional[str] = None, *, root: Optional[str] = None):
    """Export the de-identified validation records."""
    from ..warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).export(output_path)


_PACKET_README = (
    "CiteVahti review packet\n"
    "=======================\n\n"
    "A self-contained, local snapshot of a citation-integrity review — for a\n"
    "supervisor, co-author, or journal. Nothing here was transmitted anywhere.\n\n"
    "  citation-integrity-report.md    — the human-readable report (Markdown)\n"
    "  citation-integrity-report.html  — the same report, print-ready (open + Save as PDF)\n"
    "  claims.json                     — the structured claim-by-claim evidence trail,\n"
    "                                    ratings, decisions, and the audit-chain provenance\n"
    "  methods.md                      — a submission-ready methods paragraph, auto-filled\n"
    "                                    with this review's numbers (paste into your manuscript)\n\n"
    "The states record citation support from the blinded human -> AI -> adjudication\n"
    "workflow — not clinical or scientific truth. See the report's Scope & limitations.\n"
)


def export_review_packet(output_path: Optional[str] = None, *, root: Optional[str] = None) -> dict:
    """Bundle the report (Markdown + print-ready HTML) + the structured evidence/audit
    trail into one local ``.zip`` for handing off. Stdlib only; nothing is transmitted."""
    import json
    import os
    import zipfile

    from ..report import build_methods_markdown, render_html, render_markdown
    store = _open_store(root)
    rep = claim_report(root=root)
    stamp = (rep.generated_at or "report").replace(":", "-").replace(".", "-")[:19]
    out = output_path or str(store.dir / "exports" / f"review-packet-{stamp}.zip")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    members = ["citation-integrity-report.md", "citation-integrity-report.html",
               "claims.json", "methods.md", "README.txt"]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(members[0], render_markdown(rep))
        z.writestr(members[1], render_html(rep))
        z.writestr(members[2], json.dumps(rep.model_dump(mode="json"), indent=2, sort_keys=True))
        z.writestr(members[3], build_methods_markdown(store))   # submission-ready methods paragraph
        z.writestr(members[4], _PACKET_README)
    return {"output_file": out, "claim_count": rep.total, "members": members}


def export_report_docx(output_path: Optional[str] = None, *, root: Optional[str] = None) -> dict:
    """Export the report as a Word .docx (needs the optional 'docx' extra; raises a clear
    error otherwise). Local file under exports/; nothing is transmitted."""
    import os

    from ..report import render_docx
    store = _open_store(root)
    rep = claim_report(root=root)
    data = render_docx(rep)          # RuntimeError with install hint if python-docx is absent
    stamp = (rep.generated_at or "report").replace(":", "-").replace(".", "-")[:19]
    out = output_path or str(store.dir / "exports" / f"citation-integrity-report-{stamp}.docx")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)
    return {"output_file": out, "claim_count": rep.total}


def warehouse_purge(*, root: Optional[str] = None):
    """Erase the validation warehouse (consent withdrawal)."""
    from ..warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).purge()


def warehouse_configure(*, enabled: Optional[bool] = None,
                        include_claim_text: Optional[bool] = None,
                        auto_emit: Optional[bool] = None, domain: Optional[str] = None,
                        root: Optional[str] = None):
    """Set the warehouse opt-ins (enable / include-claim-text / auto-emit / domain).

    The warehouse is default-off; this is the explicit consent toggle. Only the
    fields passed are changed. Returns the resulting status.
    """
    from ..warehouse import ValidationWarehouseService

    store = _open_store(root)
    cfg = store.load_config()
    wh = cfg.validation_warehouse
    if enabled is not None:
        wh.enabled = bool(enabled)
    if include_claim_text is not None:
        wh.include_claim_text = bool(include_claim_text)
    if auto_emit is not None:
        wh.auto_emit = bool(auto_emit)
    if domain is not None:
        wh.domain = domain or None
    store.save_config(cfg)
    return ValidationWarehouseService(store).status()


# ---- AtlasVahti contribution (consented, de-identified, revocable) ----------
def atlas_contribution_preview(*, allow_claim_text: bool = False,
                               root: Optional[str] = None) -> dict:
    """Build a de-identified contribution bundle from the warehouse. No transmission."""
    from ..atlas import build_contribution_bundle
    return build_contribution_bundle(root=root, allow_claim_text=allow_claim_text)


def atlas_revoke(contribution_id: str, *, reason: Optional[str] = None,
                 root: Optional[str] = None) -> dict:
    """Build a revocation (purge) request referencing a prior contribution."""
    from ..atlas import build_revocation
    return build_revocation(contribution_id, reason=reason, root=root)


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


def _bbt_citekey_source(store):
    """A BbtCitekeySource over the configured Better BibTeX endpoint, or None. The
    source itself degrades to None per-lookup when BBT is unreachable, so callers
    fall back to minted keys without erroring."""
    try:
        from ..bbt.client import BbtClient
        from ..probe.client import HttpxClient
        from ..report.citation_export import BbtCitekeySource
        endpoints = store.load_config().endpoints
        return BbtCitekeySource(BbtClient(HttpxClient(), endpoints))
    except Exception:  # noqa: BLE001 (BBT is best-effort; minted keys are the fallback)
        return None


def cite_export(manuscript_path: str, *, claim_ids: Optional[list[str]] = None,
                root: Optional[str] = None):
    """Cite-stable export: embed a durable ``[@citekey]`` after each ACCEPTED claim
    in the manuscript Markdown and build a matching ``references.bib``.

    Prefers the paper's OWN Better BibTeX citekey (so ``[@key]`` matches the user's
    Zotero), minting a PMID/DOI key only when BBT can't confirm one. The embedded key
    is the citation's portable form — plain text that survives copy-paste and a Pandoc
    Markdown→Word conversion. Read-only over the ledger; returns the annotated text +
    bibliography (the caller writes the files).
    """
    from pathlib import Path

    from ..report.citation_export import CitationExportService
    store = _open_store(root)
    md = Path(manuscript_path).read_text(encoding="utf-8")
    return CitationExportService(store).export(
        md, claim_ids=claim_ids, citekey_source=_bbt_citekey_source(store))


def cite_export_manuscript(manuscript_path: str, *, make_docx: bool = False,
                           root: Optional[str] = None):
    """Run cite-export over a manuscript FILE and write ``<name>.cited.md`` +
    ``references.bib`` beside it (and a ``.docx`` when Pandoc is available). Returns
    the written paths, counts, key sources, and any warnings — for the panel button."""
    from ..report.citation_export import write_outputs
    result = cite_export(manuscript_path, root=root)
    # user-initiated (button) → allow the one-time Pandoc fetch for the .docx
    info = write_outputs(result, manuscript_path, make_docx=make_docx,
                         allow_pandoc_download=make_docx)
    return {**info, "injected": result.injected, "skipped": result.skipped,
            "warnings": result.warnings,
            "bbt_keys": sum(1 for e in result.entries if e.key_source == "bbt"),
            "minted_keys": sum(1 for e in result.entries if e.key_source == "minted")}


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
