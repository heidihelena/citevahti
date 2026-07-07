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
from ..schemas.rating import Subject

# Read-only groups split out (ADR-0010 PR 1a/1b); re-exported so the public
# citevahti.tools.<name> surface is unchanged. Shared factory helpers live in ._common
# (imported here so the ~60 in-facade callers, and the staying stateful functions, resolve
# them) — the neutral module the group files depend on without a cycle back to the facade.
from ._common import _intake_service, _open_store, _pubmed_provider  # noqa: F401
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
def _rating_engine(root, ai_rater):
    from ..rating import RatingEngine
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
    from ..assess import AssessmentService
    from ..rating import RatingEngine
    store = _open_store(root)
    engine = RatingEngine(store, ai_rater=ai_rater) if dual_rating else None
    return AssessmentService(store, engine).assess(
        frame_id, scheme_id, subject, human_value, reasons=reasons, rationale=rationale,
        dual_rating=dual_rating, tag_mirror=tag_mirror)


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


def model_advisor(model_id: Optional[str] = None, *, root: Optional[str] = None):
    """Which identifiable AI model to trust as a second opinion, from the live
    complementary-catch scoreboard. Read-only, writes nothing. Ranks by validated
    catches (not agreement); pass ``model_id`` and, if it rates low, it suggests a
    better-evidenced alternative."""
    from ..export import AgreementReportService
    return AgreementReportService(_open_store(root)).advise_models(model_id)


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
def add_claim(claim_text: str, claim_type: str = "other", *,
              manuscript_location: Optional[str] = None, manuscript_id: Optional[str] = None,
              project_id: Optional[str] = None, extracted_by: str = "human",
              extraction_model: Optional[str] = None, root: Optional[str] = None):
    """Record a first-class manuscript claim. Mutates no Zotero state, decides nothing."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).add_claim(
        claim_text, claim_type, manuscript_location=manuscript_location,
        manuscript_id=manuscript_id, project_id=project_id, extracted_by=extracted_by,
        extraction_model=extraction_model)


def list_claims(*, root: Optional[str] = None):
    """List recorded claims (read-only)."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).list_claims()


def claim_mark_untestable(claim_id: str, reason: Optional[str], *,
                          root: Optional[str] = None):
    """Mark a claim's cited source as outside the indexed-literature scope
    (book/chapter/grey literature), or clear the marker with ``reason=None``.
    The report then shows ``[u] untestable`` instead of ``needs_support``."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).mark_untestable(claim_id, reason)


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


def propose_revision(claim_id: str, new_text: str, *, extracted_by: str = "human",
                     extraction_model: Optional[str] = None, root: Optional[str] = None):
    """Attach a pending rewrite to a claim. Applies nothing; the human reviews the diff."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).propose_revision(
        claim_id, new_text, extracted_by=extracted_by, extraction_model=extraction_model)


def accept_revision(claim_id: str, *, expected_text: Optional[str] = None,
                    root: Optional[str] = None):
    """Apply a pending rewrite to the claim text (human action; audited before/after)."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).accept_revision(
        claim_id, expected_text=expected_text)


def reject_revision(claim_id: str, *, root: Optional[str] = None):
    """Discard a pending rewrite; the claim text is unchanged (audited)."""
    from ..claims import ClaimService
    return ClaimService(_open_store(root)).reject_revision(claim_id)


def claim_bond_status(claim_id: str, *, root: Optional[str] = None):
    """Report whether a claim's evidence assessments are stale after a revision.

    Returns the bond freshness for the claim — which claim-support ratings /
    decisions were formed against an older wording (``stale``) and so should be
    re-checked. Advisory only; nothing is invalidated."""
    from ..claims.bonds import claim_bond_status as _status
    return _status(_open_store(root), claim_id)


def link_candidates(claim_id: str, intake_batch_id: str, record_ids: Optional[list] = None, *,
                    root: Optional[str] = None):
    """Link staged intake hits to a claim as candidates (ADR-0001 step 2). No Zotero write."""
    from ..claims import CandidateService
    return CandidateService(_open_store(root)).link_from_intake(
        claim_id, intake_batch_id, record_ids=record_ids)


def list_candidates(claim_id: str, *, root: Optional[str] = None):
    """List a claim's candidate papers (read-only)."""
    from ..claims import CandidateService
    return CandidateService(_open_store(root)).list_for_claim(claim_id)


def unlink_candidate(claim_id: str, candidate_id: str, *, root: Optional[str] = None):
    """Unlink one candidate paper from a claim (the 'wrong paper' case). The
    removal is audited and non-destructive — the claim and the audit trail are
    kept; only the paper leaves active consideration."""
    cc = _open_store(root).unlink_candidate(claim_id, candidate_id)
    return {"claim_id": claim_id, "candidate_id": candidate_id,
            "remaining_candidates": len(cc.candidates)}


# ---- ADR-0001 step 3: claim-support dual rating --------------------------
def _support_engine(root, rater=None):
    from ..claims import ClaimSupportEngine
    return ClaimSupportEngine(_open_store(root), rater=rater)


def support_start(claim_id: str, candidate_id: str, *, root: Optional[str] = None):
    """Start a blinded claim-support rating for a (claim, candidate) pair."""
    return _support_engine(root).support_start(claim_id, candidate_id)


def support_commit_human(rating_id: str, value: str, *, fit=None, rationale: Optional[str] = None,
                         committed_by: str = "human", root: Optional[str] = None):
    """Commit + lock the human claim-support value (with optional PICO fit)."""
    return _support_engine(root).support_commit_human(
        rating_id, value, fit=fit, rationale=rationale, committed_by=committed_by)


def support_panel(claim_id: str, candidate_id: Optional[str] = None, *, root: Optional[str] = None):
    """Organized-panel "X of N support" aggregate (ADR-0008): how many of N independent human
    reviewers support a claim, the value distribution, raw agreement, and the confidence tier
    (1 individual · 2–7 review · 8+ guideline). Reads existing human ratings — no new rating,
    no decision. With ``candidate_id`` it summarizes that pair; without, the whole claim."""
    from ..claims.panel import claim_panel_summary, panel_summary
    store = _open_store(root)
    if candidate_id:
        return panel_summary(store, claim_id, candidate_id)
    return claim_panel_summary(store, claim_id)


def support_run_ai(rating_id: str, task_type: str = "assess", *, root: Optional[str] = None,
                   rater=None):
    """Blind advisory AI claim-support rating (needs a pinned model + a rater).

    With no rater injected, build one from config: ``off`` -> a clear error (the MCP
    assistant submits the rating instead), ``local`` / ``api`` -> the configured model.
    """
    store = _open_store(root)
    if rater is None:
        from ..claims import build_support_ai_rater
        rater = build_support_ai_rater(store.load_config())
        if rater is None:
            from ..validators.errors import AIUnavailableError
            raise AIUnavailableError(
                "AI is off — the AI second opinion is optional. Continue human-only "
                "(your rating decides), or turn it on: set 'local' or 'api' in the panel "
                "(✦ AI), or have your MCP assistant submit the rating.")
    _backfill_abstract(store, rating_id, root)   # a title alone -> the AI can only abstain
    return _support_engine(root, rater).support_run_ai(rating_id, task_type)


def _backfill_abstract(store, rating_id: str, root: Optional[str]) -> None:
    """Best-effort: if the candidate has a PMID but no abstract, fetch + save it so the
    AI (and the human) have the text the support judgment needs. Offline/failure: leave
    it as-is and let the rater abstain honestly."""
    try:
        rec = store.load_support_rating(rating_id)
        cc = store.load_candidates(rec.claim_id)
        cand = next((c for c in cc.candidates if c.candidate_id == rec.candidate_id), None)
        if cand is None or getattr(cand, "abstract", None) or not getattr(cand, "pmid", None):
            return
        hits = _pubmed_provider(root).fetch_records([cand.pmid], include_abstracts=True)
        abstract = next((getattr(h, "abstract", None) for h in hits
                         if getattr(h, "abstract", None)), None)
        if abstract:
            cand.abstract = abstract
            store.save_candidates(cc)
    except Exception:  # noqa: BLE001 (enrichment is best-effort; never block the rating)
        pass


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
    from ..claims import DecisionService
    store = _open_store(root)
    rec = DecisionService(store).decide(
        claim_id, candidate_id, final_decision, decision_reason,
        rating_id=rating_id, decided_by=decided_by)
    cfg = store.load_config()
    if cfg.validation_warehouse.enabled and cfg.validation_warehouse.auto_emit:
        from ..warehouse import ValidationWarehouseService
        ValidationWarehouseService(store, cfg).emit_for_decision(claim_id, candidate_id)
    return rec


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


def methods_statement(*, root: Optional[str] = None) -> str:
    """The submission-ready methods paragraph for *this* ledger, as Markdown — the same
    text bundled into the review packet's ``methods.md``, but viewable directly so it can
    be read or pasted without unzipping. Includes the PRISMA-style 'how the literature was
    found' disclosure (whether an LLM was in the discovery loop). Read-only."""
    from ..report import build_methods_markdown
    return build_methods_markdown(_open_store(root))


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


def import_manuscript_docx(docx_base64: str, *, root: Optional[str] = None) -> dict:
    """Convert an uploaded .docx manuscript to Markdown for the paste → review flow
    (needs the 'docx' extra). Returns the text only — the human reviews and saves it."""
    import base64
    import binascii

    from ..report import docx_to_markdown
    try:
        data = base64.b64decode(docx_base64 or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("import payload is not valid base64") from exc
    if not data:
        raise ValueError("no .docx data provided")
    md = docx_to_markdown(data)      # RuntimeError with install hint if python-docx is absent
    return {"markdown": md, "lines": md.count("\n")}


def claim_tests_prompt(manuscript: str = "") -> dict:
    """The ready-to-paste ``run_claim_tests`` choreography, optionally pre-filled with
    a manuscript. This is the bridge that closes the Word/Markdown → claims loop: after
    importing a .docx, the panel hands the reviewer the exact prompt to paste into their
    chat client, with the imported text already embedded. Single source of truth — the
    choreography text lives in ``agent.prompts``, never duplicated in the UI."""
    from ..agent.prompts import CLAIM_TEST_PROMPT_NAME, run_claim_tests_prompt
    return {"name": CLAIM_TEST_PROMPT_NAME, "prompt": run_claim_tests_prompt(manuscript or "")}


def topic_screen_prompt(topic: str = "") -> dict:
    """The ready-to-paste ``screen_topic`` choreography (ADR-0008, Layer 0), optionally
    pre-filled with a topic. The panel's "Screen a topic" button hands the reviewer this
    prompt to paste into their chat client; the assistant then proposes candidate claims +
    nearby evidence (leads, not verdicts) and hands off to ``run_claim_tests``. The panel
    never calls an AI itself (ADR-0007); the choreography text lives in ``agent.prompts``."""
    from ..agent.prompts import SCREEN_TOPIC_PROMPT_NAME, screen_topic_prompt
    return {"name": SCREEN_TOPIC_PROMPT_NAME, "prompt": screen_topic_prompt(topic or "")}


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


def list_decisions(claim_id: str, *, root: Optional[str] = None):
    """List a claim's final decisions (read-only)."""
    from ..claims import DecisionService
    return DecisionService(_open_store(root)).list_for_claim(claim_id)


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
def claim_report(*, claim_ids: Optional[list] = None, root: Optional[str] = None):
    """Run citation-integrity tests over the project's claims (read-only 4-state report)."""
    from ..report import ClaimReportService
    return ClaimReportService(_open_store(root)).report(claim_ids=claim_ids)


def triage(*, root: Optional[str] = None):
    """Risk-first triage: the few claims worth your attention right now, worst-first,
    each with the reason and the next action. Read-only — the friendly front door to a
    review (review these, not all of them)."""
    from ..report import ClaimReportService
    from ..risk import triage as _triage
    report = ClaimReportService(_open_store(root)).report()
    return _triage(report)


# final_decision (schemas/decision.py) -> the four verdict hues + unrated. Kept in one
# place so the panel map and any future export agree on the mapping.
_MAP_VERDICT = {"accept": "accept", "accepted_with_caution": "caution",
                "needs_second_review": "review", "reject": "reject"}


def evidence_map(*, root: Optional[str] = None) -> dict:
    """Read-only claim<->evidence graph for the panel's Atlas map (and figure export).

    Nodes are claims and the *deduplicated* cited papers (one node per PMID/DOI, so a
    paper cited for several claims is a single shared node). Each edge is one
    (claim, candidate) pair carrying the human support rating, the **blinded** AI support
    (``"hidden"`` until the human has rated — the blinding rule is applied once, in
    ClaimReportService, never re-derived here), the final decision mapped to a verdict
    hue, and the retraction / staleness flags. A retracted paper is flagged independent
    of any rating. Mutates nothing; decides nothing."""
    from ..report import ClaimReportService

    store = _open_store(root)
    rep = ClaimReportService(store).report()

    def paper_key(pmid, doi, title):
        if pmid:
            return f"pmid:{pmid}"
        if doi:
            return f"doi:{str(doi).strip().lower()}"
        return f"title:{(title or '').strip().lower()[:80]}"

    papers: dict[str, dict] = {}
    edges: list[dict] = []
    claims: list[dict] = []
    for row in rep.rows:
        claims.append({"id": row.claim_id, "text": row.claim_text,
                       "type": row.claim_type, "location": row.manuscript_location,
                       "state": row.state, "code": row.code.strip(),
                       "untestable": bool(row.untestable_reason)})
        # candidate metadata (journal/year) for nicer paper labels; best-effort
        try:
            cands = {c.candidate_id: c for c in store.load_candidates(row.claim_id).candidates}
        except Exception:
            cands = {}
        for ev in row.evidence:
            pid = paper_key(ev.pmid, ev.doi, ev.title)
            node = papers.get(pid)
            if node is None:
                c = cands.get(ev.candidate_id)
                papers[pid] = {"id": pid, "title": ev.title, "pmid": ev.pmid, "doi": ev.doi,
                               "journal": getattr(c, "journal", None), "year": getattr(c, "year", None),
                               "retracted": bool(ev.retracted)}
            else:
                node["retracted"] = node["retracted"] or bool(ev.retracted)
                if not node.get("title") and ev.title:
                    node["title"] = ev.title
            edges.append({"claim_id": row.claim_id, "paper_id": pid,
                          "human_support": ev.human_support, "ai_support": ev.ai_support,
                          "decision": _MAP_VERDICT.get(ev.final_decision or "", "unrated"),
                          "final_decision": ev.final_decision, "agreement": ev.agreement,
                          "stale": bool(ev.stale)})

    prov = rep.provenance
    return {"claims": claims, "papers": list(papers.values()), "edges": edges,
            "counts": {"claims": len(claims), "papers": len(papers), "links": len(edges)},
            "generated_at": rep.generated_at, "warnings": rep.warnings,
            "retraction_source": getattr(prov, "retraction_source", None),
            "last_retraction_scan_at": getattr(prov, "last_retraction_scan_at", None)}


def check_paragraph(text: str, *, root: Optional[str] = None):
    """Check-a-paragraph: for a snippet you just wrote, which sentences map to claims
    you've already vetted, which need attention, and which are new/untracked. Read-only,
    no AI — the everyday in-the-writing loop. Returns a per-sentence status + tally."""
    from ..report.paragraph import check_paragraph as _check
    return _check(_open_store(root), text or "")


def draft_context(*, root: Optional[str] = None) -> dict:
    """Read-only: the researcher's ACCEPTED claims, each with the citekey to cite it by —
    the user's own Better BibTeX key is resolved by cite-export; here we give the stable
    key minted from the paper's PMID/DOI (never an invented one). An accepted claim with
    no resolvable identifier is returned ``cited: False`` and flagged, so the draft skill
    can mark it as needing a source rather than fabricating one. Records nothing, writes
    nothing — it just gathers vetted claims to draft from."""
    from ..report import ClaimReportService
    from ..report.citation_export import mint_citekey
    from ..report.claim_report import _ACCEPTING

    rep = ClaimReportService(_open_store(root)).report()
    items = []
    for row in rep.rows:
        if row.state != "accepted":
            continue
        fresh = [e for e in row.evidence if e.final_decision in _ACCEPTING and not e.stale]
        if not fresh:
            items.append({"claim_text": row.claim_text, "citekey": None, "cited": False,
                          "reason": "the citation went stale (claim reworded) — re-accept to refresh"})
            continue
        ev = fresh[0]
        citekey = mint_citekey(ev.pmid, ev.doi)
        if not citekey:
            items.append({"claim_text": row.claim_text, "citekey": None, "cited": False,
                          "reason": "the accepted paper has no PMID or DOI to cite by"})
            continue
        items.append({"claim_text": row.claim_text, "citekey": citekey, "cited": True})
    return {"claims": items, "accepted": len(items),
            "cited": sum(1 for i in items if i["cited"])}


_CHAT_FRAMING = (
    "You are CiteVahti's assistant, helping a researcher check that their manuscript's "
    "claims are supported by the sources cited for them. Help them find candidate claims, "
    "screen a topic, and refine wording. The researcher records every support rating and "
    "decision themselves in the panel — do NOT declare whether a source supports a claim "
    "before they have rated it; present evidence neutrally so you don't anchor them. Never "
    "assert that a paper proves a claim, or that a manuscript is correct or "
    "publication-ready: CiteVahti checks citation support, not truth."
)


def chat(message: str, *, root: Optional[str] = None, poster=None) -> dict:
    """One advisory chat turn with the CONFIGURED model — a local Ollama / LM Studio model
    (nothing leaves your machine) or your own API key — reusing the same connection plumbing
    as the AI rater. It RECORDS nothing, calls no tools, and writes nothing: a conversational
    helper, never the blinded rating path. Returns ``ai_off`` when no model is configured.
    ``poster`` is injectable for tests."""
    from ..rating.ai import chat_completion, resolve_ai_connection

    config = _open_store(root).load_config()
    conn = resolve_ai_connection(config)
    if conn is None:
        return {"status": "ai_off", "reply": None,
                "message": "No model is configured. Set one in AI settings — a local Ollama "
                           "model keeps everything on your machine."}
    prompt = f"{_CHAT_FRAMING}\n\nResearcher: {message or ''}\n\nAssistant:"
    reply = chat_completion(shape=conn["shape"], endpoint=conn["endpoint"],
                            model=config.ai_provenance.model_id, prompt=prompt,
                            api_key=conn["api_key"], poster=poster,
                            timeout=config.ai_connection.request_timeout_s)
    return {"status": "ok", "model": config.ai_provenance.model_id, "reply": reply}


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
