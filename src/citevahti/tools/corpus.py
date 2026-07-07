"""Corpus snapshots, staleness diffs, surveillance, and map bootstrap (ADR-0010 PR 1j).

Longitudinal corpus state: a hashed read-only snapshot of corpus + evidence-map state,
diffs between snapshots (optionally flagging staleness on the ledger), a saved-query
surveillance refresh (stages new hits pre-decision, from the query's own last-run date),
and deterministic evidence-map seeding from a guideline file (dry-run by default).
Ledger-only writes where they write at all; no Zotero library write.

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ..probe.client import HttpxClient
from ..schemas.common import LibrarySelector
from ..schemas.config import Endpoints
from ._common import _intake_service, _open_store


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
