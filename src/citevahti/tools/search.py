"""Read-only external literature lookups (ADR-0010 PR 1b — read-only group).

Best-effort, network-backed lookups that resolve identifiers or search external corpora
and return plain data. None of them writes to a Zotero library, the ledger, or the
filesystem — they degrade to empty/`{}` offline and never block the workflow. A wrong DOI
is worse than none, so identifier resolution is strict, never fuzzy-guessed.

The stateful cousins that live near these in the workflow — ``literature_search`` (stages
intake), ``backfill_candidate_dois`` / ``recheck_library`` / ``scan_retractions`` /
``scan_licenses`` (all mutate candidate records) — stay in the facade for a later,
write-aware PR (ADR-0010 §3: read-only first, stateful later).

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ._common import _open_store, _pubmed_provider


def resolve_dois(pmids: list, *, root: Optional[str] = None, http=None, provider=None) -> dict:
    """Resolve missing DOIs from PMIDs via NCBI — authoritative, never a guess.

    Returns ``{pmid: doi}`` only for records that actually have a DOI. Offline or on
    any NCBI error it returns ``{}`` (resolution is best-effort and never blocks the
    rest of the workflow). No fuzzy/title matching: a wrong DOI is worse than none."""
    ids = [str(p) for p in (pmids or []) if p]
    if not ids:
        return {}
    if provider is None:
        provider = _pubmed_provider(root, http)
    try:
        hits = provider.fetch_records(ids)
    except Exception:  # noqa: BLE001 — NCBI down / offline -> resolve nothing
        return {}
    return {h.pmid: h.doi for h in hits if h.pmid and h.doi}


def resolve_dois_by_title(titles: list, *, root: Optional[str] = None, http=None, client=None) -> dict:
    """CrossRef title → DOI for candidates lacking any identifier. Strict matching
    (a wrong DOI is worse than none); returns ``{title: doi}`` only for strong
    matches. Best-effort: offline/ambiguous titles are simply omitted."""
    wanted = {t for t in (titles or []) if t}
    if not wanted:
        return {}
    if client is None:
        from ..crossref import CrossrefClient
        try:
            mailto = _open_store(root).load_config().pubmed.contact_email
        except Exception:  # noqa: BLE001
            mailto = None
        client = CrossrefClient(http=http, mailto=mailto)
    out = {}
    for t in sorted(wanted):
        try:
            doi = client.doi_for_title(t)
        except Exception:  # noqa: BLE001
            doi = None
        if doi:
            out[t] = doi
    return out


def openalex_search(query: str, max_results: int = 15, *, root: Optional[str] = None,
                    http=None, client=None) -> list:
    """OpenAlex search → normalized hits (the API-backed alternative to Scholar)."""
    if client is None:
        from ..openalex import OpenAlexClient
        try:
            mailto = _open_store(root).load_config().pubmed.contact_email
        except Exception:  # noqa: BLE001
            mailto = None
        client = OpenAlexClient(http=http, mailto=mailto)
    try:
        return client.search(query, max_results)
    except Exception:  # noqa: BLE001
        return []


def semanticscholar_search(query: str, max_results: int = 15, *, root: Optional[str] = None,
                           http=None, client=None) -> list:
    """Semantic Scholar search → normalized hits (another broad, API-backed source)."""
    if client is None:
        from ..semscholar import SemanticScholarClient
        client = SemanticScholarClient(http=http)
    try:
        return client.search(query, max_results)
    except Exception:  # noqa: BLE001
        return []


def check_update(*, http=None) -> dict:
    """Ask PyPI whether a newer CiteVahti release is published. Read-only, never installs;
    user-initiated (no launch-time or timed phone-home). Contacts pypi.org only when
    called. Returns current/latest/update_available + a plain-language message."""
    from ..update_check import check_update as _check
    return _check(http=http)
