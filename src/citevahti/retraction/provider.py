"""Retraction provider seam.

A real provider would consult PubMed publication types / Crossref / Retraction
Watch by DOI/PMID. Step 7 ships a fake, deterministic provider for tests and a
PubMed-compatible shape. Title is never used for retraction truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from ..intake.dedupe import normalize_doi, normalize_pmid


class RetractionProviderUnavailable(Exception):
    code = "provider_unavailable"


@dataclass
class RetractionResult:
    retracted: bool
    status: str = "retracted"
    source: Optional[str] = None
    notice_url: Optional[str] = None


@runtime_checkable
class RetractionProvider(Protocol):
    # Returns a RetractionResult when retracted, None when not, raises
    # RetractionProviderUnavailable when offline. DOI/PMID only -- never title.
    def lookup(self, *, doi: Optional[str] = None,
               pmid: Optional[str] = None) -> Optional[RetractionResult]: ...


class FakeRetractionProvider:
    def __init__(self, retracted_dois=None, retracted_pmids=None, available: bool = True,
                 source: str = "fake_retraction_db") -> None:
        self.dois = {normalize_doi(d) for d in (retracted_dois or [])}
        self.pmids = {normalize_pmid(p) for p in (retracted_pmids or [])}
        self.available = available
        self.source = source

    def lookup(self, *, doi=None, pmid=None) -> Optional[RetractionResult]:
        if not self.available:
            raise RetractionProviderUnavailable("retraction provider offline")
        nd, np = normalize_doi(doi), normalize_pmid(pmid)
        if (nd and nd in self.dois) or (np and np in self.pmids):
            return RetractionResult(retracted=True, source=self.source,
                                    notice_url="https://example.org/retraction")
        return None
