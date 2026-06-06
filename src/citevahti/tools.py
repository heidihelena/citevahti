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

from .cite import CiteService, CiteTarget
from .probe.client import HttpxClient
from .probe.probe import CapabilityReport
from .schemas.common import ItemRef, LibrarySelector, ToolResult
from .schemas.config import Config, Endpoints
from .schemas.rating import Subject
from .validators import authorize_rating_task, require_model_pinned
from .zotero import ZoteroService


def _todo(step: int, tool: str):
    raise NotImplementedError(f"{tool}: scheduled for build order step {step}; not yet approved")


def _zotero(endpoints: Optional[Endpoints], capability: Optional[CapabilityReport]) -> ZoteroService:
    return ZoteroService(HttpxClient(), endpoints, capability)


def _cite(endpoints: Optional[Endpoints], capability: Optional[CapabilityReport]) -> CiteService:
    return CiteService(HttpxClient(), endpoints, capability)


# ---- step 2: read/discover (zot_*) + cite -------------------------------
# Thin façade over the read-only Zotero local API and Better BibTeX. All reads
# honor the library selector; cite never invents keys and fails on unresolved
# keys; both degrade honestly when their backend is absent.

def zot_search(query: str, library: LibrarySelector = "personal", limit: Optional[int] = None,
               *, endpoints: Optional[Endpoints] = None,
               capability: Optional[CapabilityReport] = None) -> ToolResult:
    return _zotero(endpoints, capability).zot_search(query, library, limit)


def zot_item(ref: ItemRef, *, endpoints: Optional[Endpoints] = None,
             capability: Optional[CapabilityReport] = None) -> ToolResult:
    return _zotero(endpoints, capability).zot_item(ref)


def zot_collections(library: LibrarySelector = "personal", *,
                    endpoints: Optional[Endpoints] = None,
                    capability: Optional[CapabilityReport] = None) -> ToolResult:
    return _zotero(endpoints, capability).zot_collections(library)


def zot_attachments(ref: ItemRef, *, endpoints: Optional[Endpoints] = None,
                    capability: Optional[CapabilityReport] = None) -> ToolResult:
    return _zotero(endpoints, capability).zot_attachments(ref)


def cite(target: CiteTarget, format: str = "pandoc", *,
         endpoints: Optional[Endpoints] = None,
         capability: Optional[CapabilityReport] = None) -> ToolResult:
    return _cite(endpoints, capability).cite(target, format)


# ---- step 3: bib_sync + evidence_map ------------------------------------
def bib_sync(targets: dict, output_dir: Optional[str] = None,
             export_format: str = "bibtex", include_cited_only: bool = True,
             make_master: bool = True, fail_on_orphans: bool = False,
             library: LibrarySelector = "personal", *,
             endpoints: Optional[Endpoints] = None, provider=None, root: Optional[str] = None):
    """Multi-file citation sync. ``targets={"paths": [...]}``. Returns a BibSyncReport.

    Resolves citekeys by exact match through Better BibTeX (never inventing keys)
    and degrades honestly when BBT is absent.
    """
    from .bibsync import BbtBibProvider, BibSyncService
    from .state import CiteVahtiStore

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
    from .bbt.client import BbtClient
    from .retrieval import ZoteroApiTextSource
    from .zotero import ZoteroService

    http = HttpxClient()
    return ZoteroApiTextSource(ZoteroService(http, endpoints), BbtClient(http, endpoints))


def extract(subject: ItemRef, fields: Optional[list[str]] = None, mode: str = "assistive",
            require_passage: bool = False, library: LibrarySelector = "personal", *,
            source=None, endpoints: Optional[Endpoints] = None):
    """Assistive, deterministic field extraction. Returns an ExtractResult.
    Never guesses; never writes to the evidence map."""
    from .extract import ExtractService

    src = source or _text_source(endpoints)
    return ExtractService(src).extract(subject, fields, mode=mode,
                                       require_passage=require_passage, library=library)


def claim_check(claim_text: str, citekeys: list[str], context: Optional[str] = None,
                require_page: bool = False, library: LibrarySelector = "personal", *,
                source=None, endpoints: Optional[Endpoints] = None):
    """Deterministic lexical claim support. Returns a ClaimCheckResult.
    Never asserts truth; never invents keys; exact citekey resolution only."""
    from .claimcheck import ClaimCheckService

    src = source or _text_source(endpoints)
    return ClaimCheckService(src).check(claim_text, citekeys, context=context,
                                        require_page=require_page, library=library)


# ---- step 5: literature_search + import_results (PubMed) ----------------
def _intake_service(root: Optional[str], library, endpoints, provider, library_index):
    import os

    from .intake import IntakeService, ZoteroLibraryIndex
    from .pubmed import PubMedProvider
    from .state import CiteVahtiStore
    from .zotero import ZoteroService

    from .credentials import NCBI_API_KEY, get_credential_store, resolve_secret

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
def _open_store(root: Optional[str]):
    import os

    from .state import CiteVahtiStore
    store = CiteVahtiStore(root or os.getcwd())
    if not store.exists():
        raise ValueError(f"{store.dir} is not initialized; run `citevahti init` first")
    return store


def _corpus_source(endpoints: Optional[Endpoints]):
    from .bbt.client import BbtClient
    from .corpus import ZoteroCorpusSource
    from .probe.probe import run_probes
    from .zotero import ZoteroService

    http = HttpxClient()
    cap = run_probes(http, endpoints)
    return ZoteroCorpusSource(ZoteroService(http, endpoints, cap), BbtClient(http, endpoints), cap)


def snapshot(label: Optional[str] = None, library: LibrarySelector = "personal",
             include_fulltext_hashes: bool = False, include_retraction_status: bool = False, *,
             root: Optional[str] = None, endpoints: Optional[Endpoints] = None, source=None):
    """Read-only hashed capture of corpus + evidence-map state."""
    from .corpus import SnapshotService
    store = _open_store(root)
    return SnapshotService(store, source or _corpus_source(endpoints)).snapshot(
        label=label, library=library, include_fulltext_hashes=include_fulltext_hashes,
        include_retraction_status=include_retraction_status)


def corpus_diff(from_snapshot_id: str, to_snapshot_id: Optional[str] = None,
                compare_to_current: bool = False, mark_stale: bool = False,
                library: LibrarySelector = "personal", *, root: Optional[str] = None,
                endpoints: Optional[Endpoints] = None, source=None):
    """Compare snapshots (or snapshot vs current) and report/flag staleness."""
    from .corpus import CorpusDiffService
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
    from .bbt.client import BbtClient
    from .bootstrap import MapBootstrapService
    from .retrieval import ZoteroApiTextSource
    from .zotero import ZoteroService

    store = _open_store(root)
    if resolver is None:
        http = HttpxClient()
        resolver = ZoteroApiTextSource(ZoteroService(http, endpoints), BbtClient(http, endpoints))
    return MapBootstrapService(store, resolver).bootstrap(
        guideline_path, bibliography_path=bibliography_path, library=library, dry_run=dry_run)


# ---- step 7: dual-rating engine + assess + retraction + prisma ----------
def _rating_engine(root, ai_rater):
    from .rating import RatingEngine
    return RatingEngine(_open_store(root), ai_rater=ai_rater)


def rating_start(frame_id: str, scheme_id: str, subject: Subject, domain_id: Optional[str] = None,
                 *, root: Optional[str] = None):
    return _rating_engine(root, None).rating_start(frame_id, scheme_id, subject, domain_id)


def rating_commit_human(rating_id: str, value: str, rationale: Optional[str] = None,
                        reasons: Optional[list[str]] = None, source_passages=None,
                        committed_by: str = "human", *, root: Optional[str] = None):
    return _rating_engine(root, None).rating_commit_human(
        rating_id, value, rationale=rationale, reasons=reasons, source_passages=source_passages,
        committed_by=committed_by)


def rating_run_ai(rating_id: str, task_type: str, *, root: Optional[str] = None, ai_rater=None):
    """Blind AI second rating. Refuses unallowed/assist tasks; requires a model pin."""
    return _rating_engine(root, ai_rater).rating_run_ai(rating_id, task_type)


def rating_compare(rating_id: str, *, root: Optional[str] = None):
    return _rating_engine(root, None).rating_compare(rating_id)


def rating_adjudicate(rating_id: str, final_value: str, rationale: str, decider: str = "human",
                      *, root: Optional[str] = None):
    return _rating_engine(root, None).rating_adjudicate(rating_id, final_value, rationale, decider)


def assess(frame_id: str, scheme_id: str, subject: Subject, human_value: str,
           reasons: Optional[list[str]] = None, rationale: Optional[str] = None,
           dual_rating: bool = False, tag_mirror: bool = False, *, root: Optional[str] = None,
           ai_rater=None):
    """Record a human-chosen controlled value. Never computes/suggests/pre-fills."""
    from .assess import AssessmentService
    from .rating import RatingEngine
    store = _open_store(root)
    engine = RatingEngine(store, ai_rater=ai_rater) if dual_rating else None
    return AssessmentService(store, engine).assess(
        frame_id, scheme_id, subject, human_value, reasons=reasons, rationale=rationale,
        dual_rating=dual_rating, tag_mirror=tag_mirror)


def retraction_scan(selection: Optional[dict] = None, library: LibrarySelector = "personal",
                    mark_stale: bool = False, *, root: Optional[str] = None, provider=None):
    """DOI/PMID retraction scan; never title-only; degrades honestly offline."""
    from .retraction import FakeRetractionProvider, RetractionScanService
    store = _open_store(root)
    if provider is None:
        # No live retraction provider is configured in step 7 -> degrade honestly.
        provider = FakeRetractionProvider(available=False)
    return RetractionScanService(store, provider).scan(selection, library=library,
                                                       mark_stale=mark_stale)


def prisma_ledger(question_id: str, action: str, payload: Optional[dict] = None, *,
                  root: Optional[str] = None):
    """Human-only PRISMA flow accounting. AI votes are rating_id references only."""
    from .prisma import PrismaLedgerService
    return PrismaLedgerService(_open_store(root)).prisma_ledger(question_id, action, payload)


# ---- step 8: evidence_export + agreement_report -------------------------
def aggregate_ratings(frame_id: str, actor_ids: Optional[list[str]] = None):
    """Refuses to aggregate across mismatched frame_version or scheme_id."""
    _todo(8, "aggregate_ratings")


def evidence_export(selection: Optional[dict] = None, formats: Optional[list[str]] = None,
                    include_provenance: bool = False, include_ai_values: bool = False,
                    output_dir: Optional[str] = None, *, root: Optional[str] = None):
    """Neutral CSV/Markdown/CSL-JSON evidence tables. Read-only; no judgments."""
    from .export import EvidenceExportService
    return EvidenceExportService(_open_store(root)).export(
        selection=selection, formats=formats, include_provenance=include_provenance,
        include_ai_values=include_ai_values, output_dir=output_dir)


def agreement_report(filters: Optional[dict] = None, metrics: Optional[list[str]] = None,
                     output_formats: Optional[list[str]] = None, output_dir: Optional[str] = None,
                     *, root: Optional[str] = None):
    """Human-AI agreement metrics + method-transparency section. Read-only."""
    from .export import AgreementReportService
    return AgreementReportService(_open_store(root)).report(
        filters=filters, metrics=metrics, output_formats=output_formats, output_dir=output_dir)


# ---- step 9: guarded write-back -----------------------------------------
def _writeback(root, *, service=None, dedupe_index=None, tag_reader=None):
    if service is not None:
        return service
    from .writeback import WritebackService, make_backend
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
            secrets_backend: str = "system_keyring", validate: bool = True,
            credential_store=None, validators="auto"):
    """Capture non-secret identifiers (config) and secret keys (OS keyring/env).

    Secrets are held in memory, validated where possible, then stored; they are
    never written to config or echoed back.
    """
    from .onboarding import LiveValidators, OnboardingService

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
        secrets_backend=secrets_backend, validate=validate)


# ---- ADR-0001 step 1: claims --------------------------------------------
def add_claim(claim_text: str, claim_type: str = "other", *,
              manuscript_location: Optional[str] = None, manuscript_id: Optional[str] = None,
              project_id: Optional[str] = None, extracted_by: str = "human",
              extraction_model: Optional[str] = None, root: Optional[str] = None):
    """Record a first-class manuscript claim. Mutates no Zotero state, decides nothing."""
    from .claims import ClaimService
    return ClaimService(_open_store(root)).add_claim(
        claim_text, claim_type, manuscript_location=manuscript_location,
        manuscript_id=manuscript_id, project_id=project_id, extracted_by=extracted_by,
        extraction_model=extraction_model)


def list_claims(*, root: Optional[str] = None):
    """List recorded claims (read-only)."""
    from .claims import ClaimService
    return ClaimService(_open_store(root)).list_claims()


def zotero_new_key_url(name: str = "CiteVahti", *, groups: str = "none") -> str:
    """The pre-filled Zotero new-key page (one click → Save → copy).

    ``groups`` (none|read|write) pre-selects shared/group-library access.
    """
    from .zotero import new_key_url
    return new_key_url(name, groups=groups)


def connect_zotero(api_key: str, *, require_write: bool = True, root: Optional[str] = None,
                   http=None, credential_store=None):
    """Validate a pasted Zotero key, learn the userID, store it, enable guarded write.

    The key is stored in the OS keychain and never written to config or echoed back.
    """
    from .zotero import ZoteroConnectService
    return ZoteroConnectService(_open_store(root), http=http,
                                credential_store=credential_store).connect(
        api_key, require_write=require_write)


def propose_revision(claim_id: str, new_text: str, *, extracted_by: str = "human",
                     extraction_model: Optional[str] = None, root: Optional[str] = None):
    """Attach a pending rewrite to a claim. Applies nothing; the human reviews the diff."""
    from .claims import ClaimService
    return ClaimService(_open_store(root)).propose_revision(
        claim_id, new_text, extracted_by=extracted_by, extraction_model=extraction_model)


def accept_revision(claim_id: str, *, expected_text: Optional[str] = None,
                    root: Optional[str] = None):
    """Apply a pending rewrite to the claim text (human action; audited before/after)."""
    from .claims import ClaimService
    return ClaimService(_open_store(root)).accept_revision(
        claim_id, expected_text=expected_text)


def reject_revision(claim_id: str, *, root: Optional[str] = None):
    """Discard a pending rewrite; the claim text is unchanged (audited)."""
    from .claims import ClaimService
    return ClaimService(_open_store(root)).reject_revision(claim_id)


def link_candidates(claim_id: str, intake_batch_id: str, record_ids: Optional[list] = None, *,
                    root: Optional[str] = None):
    """Link staged intake hits to a claim as candidates (ADR-0001 step 2). No Zotero write."""
    from .claims import CandidateService
    return CandidateService(_open_store(root)).link_from_intake(
        claim_id, intake_batch_id, record_ids=record_ids)


def list_candidates(claim_id: str, *, root: Optional[str] = None):
    """List a claim's candidate papers (read-only)."""
    from .claims import CandidateService
    return CandidateService(_open_store(root)).list_for_claim(claim_id)


# ---- ADR-0001 step 3: claim-support dual rating --------------------------
def _support_engine(root, rater=None):
    from .claims import ClaimSupportEngine
    return ClaimSupportEngine(_open_store(root), rater=rater)


def support_start(claim_id: str, candidate_id: str, *, root: Optional[str] = None):
    """Start a blinded claim-support rating for a (claim, candidate) pair."""
    return _support_engine(root).support_start(claim_id, candidate_id)


def support_commit_human(rating_id: str, value: str, *, fit=None, rationale: Optional[str] = None,
                         committed_by: str = "human", root: Optional[str] = None):
    """Commit + lock the human claim-support value (with optional PICO fit)."""
    return _support_engine(root).support_commit_human(
        rating_id, value, fit=fit, rationale=rationale, committed_by=committed_by)


def support_run_ai(rating_id: str, task_type: str = "assess", *, root: Optional[str] = None,
                   rater=None):
    """Blind advisory AI claim-support rating (needs a pinned model + a rater)."""
    return _support_engine(root, rater).support_run_ai(rating_id, task_type)


def support_compare(rating_id: str, *, root: Optional[str] = None):
    """Compare human vs AI support; concordance locks in the human value."""
    return _support_engine(root).support_compare(rating_id)


def support_adjudicate(rating_id: str, final_value: str, rationale: str, decider: str = "human",
                       *, root: Optional[str] = None):
    """Human/panel adjudication of a discordant support rating (only path to final)."""
    return _support_engine(root).support_adjudicate(rating_id, final_value, rationale, decider)


def get_support_rating(rating_id: str, *, root: Optional[str] = None):
    """Load a claim-support rating (read-only)."""
    return _open_store(root).load_support_rating(rating_id)


# ---- ADR-0001 step 4: final decisions ------------------------------------
def decide(claim_id: str, candidate_id: str, final_decision: str, decision_reason: str, *,
           rating_id: Optional[str] = None, decided_by: str = "human", root: Optional[str] = None):
    """Record the human-owned final decision for a (claim, candidate) pair.

    If the validation warehouse is enabled with auto_emit, a de-identified
    validation record is appended (the label emerges from the workflow)."""
    from .claims import DecisionService
    store = _open_store(root)
    rec = DecisionService(store).decide(
        claim_id, candidate_id, final_decision, decision_reason,
        rating_id=rating_id, decided_by=decided_by)
    cfg = store.load_config()
    if cfg.validation_warehouse.enabled and cfg.validation_warehouse.auto_emit:
        from .warehouse import ValidationWarehouseService
        ValidationWarehouseService(store, cfg).emit_for_decision(claim_id, candidate_id)
    return rec


def warehouse_status(*, root: Optional[str] = None):
    """De-identified validation warehouse status (read-only)."""
    from .warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).status()


def warehouse_emit(claim_id: str, candidate_id: str, *, root: Optional[str] = None):
    """Emit one de-identified validation record for a (claim, candidate). No-op if disabled."""
    from .warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).emit_for_decision(claim_id, candidate_id)


def warehouse_export(output_path: Optional[str] = None, *, root: Optional[str] = None):
    """Export the de-identified validation records."""
    from .warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).export(output_path)


def warehouse_purge(*, root: Optional[str] = None):
    """Erase the validation warehouse (consent withdrawal)."""
    from .warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).purge()


def list_decisions(claim_id: str, *, root: Optional[str] = None):
    """List a claim's final decisions (read-only)."""
    from .claims import DecisionService
    return DecisionService(_open_store(root)).list_for_claim(claim_id)


# ---- ADR-0001 step 5: decision-gated write transactions + undo -----------
def _transaction_service(root):
    from .writeback import TransactionService, make_backend
    store = _open_store(root)
    return TransactionService(store, make_backend(store.load_config()))


def commit_decision(decision_id: str, *, collection_key: Optional[str] = None,
                    library: str = "personal", dry_run: bool = True,
                    confirm_token: Optional[str] = None, allow_unverified_dedupe: bool = False,
                    root: Optional[str] = None):
    """Validated, decision-gated Zotero write (preview by default). Enforces the §6 chain.

    A confirmed write (``dry_run=False``) REQUIRES ``confirm_token`` from a prior
    preview — agent-facing callers cannot one-call write without that approval step.
    """
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
def claim_report(*, claim_ids: Optional[list] = None, root: Optional[str] = None):
    """Run citation-integrity tests over the project's claims (read-only 4-state report)."""
    from .report import ClaimReportService
    return ClaimReportService(_open_store(root)).report(claim_ids=claim_ids)
