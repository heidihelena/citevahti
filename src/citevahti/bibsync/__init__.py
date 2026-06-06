"""Multi-file citation sync (`bib_sync`).

Scans Markdown/Quarto/Rmd/LaTeX sources, extracts citekeys (Pandoc + LaTeX),
resolves them by exact match through a Better BibTeX seam (never inventing
keys), reports orphans/unused, and -- when resolution succeeds -- exports
per-file and merged-master bibliographies. Degrades honestly when BBT is absent.
"""

from .provider import (
    BibProvider,
    BbtBibProvider,
    BibProviderUnavailable,
    StaticBibProvider,
)
from .service import BibSyncService

__all__ = [
    "BibSyncService",
    "BibProvider",
    "BbtBibProvider",
    "StaticBibProvider",
    "BibProviderUnavailable",
]
