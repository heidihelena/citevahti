"""Literature intake + candidate-record maintenance (ADR-0010 PR 1i — stateful group).

Staging search results (pre-decision), and the candidate-record maintenance scans:
backfill missing DOIs, re-check the live Zotero library for dedupe, flag retracted papers,
and fill reuse-licence fields. ``literature_search`` / ``import_results`` stage intake but
never decide inclusion or import into Zotero; the scans WRITE candidate updates to the local
audited ledger (and log an audit timestamp so "last checked" is distinguishable from
"never"). None of this touches a Zotero library — that is ``tools/writeback.py``.

Depends forward on already-split groups (no cycle): ``claim_report`` from ``.reports`` (the
per-claim candidate iterator) and ``resolve_dois`` / ``resolve_dois_by_title`` from
``.search`` (the read-only DOI lookups the backfill drives).

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ..probe.client import HttpxClient
from ..schemas.common import LibrarySelector
from ..schemas.config import Endpoints
from ._common import _intake_service, _open_store
from .reports import claim_report
from .search import resolve_dois, resolve_dois_by_title


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


def import_results(source: dict, format: str, question_id: Optional[str] = None,
                   source_label: Optional[str] = None, library: LibrarySelector = "personal", *,
                   root: Optional[str] = None, endpoints: Optional[Endpoints] = None,
                   library_index=None):
    """Manual fallback staging from RIS/CSV/BibTeX (pre-decision). No Zotero import."""
    # provider not needed for manual import
    svc = _intake_service(root, library, endpoints, provider="__manual__", library_index=library_index)
    return svc.import_results(source, format, question_id=question_id,
                              source_label=source_label, library=library)


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
