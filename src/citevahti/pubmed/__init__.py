"""PubMed literature search provider (NCBI E-utilities) — the primary of the
search providers (see also openalex/semscholar/crossref).

CiteVahti runs a *user-supplied* PubMed query and stages results. It never
designs/rewrites the query, never ranks beyond PubMed return order, and never
decides inclusion. Degrades honestly when the email env is missing or PubMed is
unreachable -- no fake hits.
"""

from .provider import (
    LiteratureProvider,
    ProviderHit,
    ProviderSearchResult,
    PubMedProvider,
    PubMedUnavailable,
    RateLimiter,
)

__all__ = [
    "LiteratureProvider",
    "PubMedProvider",
    "ProviderHit",
    "ProviderSearchResult",
    "RateLimiter",
    "PubMedUnavailable",
]
