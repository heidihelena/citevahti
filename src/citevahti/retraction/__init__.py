"""DOI/PMID-based retraction scanning (step 7).

Online tool behind a provider seam; tests use a fake provider. Never relies on
title-only matching for retraction truth; degrades honestly when offline.
"""

from .provider import (
    FakeRetractionProvider,
    RetractionProvider,
    RetractionProviderUnavailable,
    RetractionResult,
)
from .service import RetractionScanService

__all__ = [
    "RetractionScanService",
    "RetractionProvider",
    "FakeRetractionProvider",
    "RetractionResult",
    "RetractionProviderUnavailable",
]
