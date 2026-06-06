"""Claims: the first-class spine of the evidence-decision ledger (ADR-0001)."""

from .candidates import CandidateService
from .decisions import DecisionService
from .service import ClaimService
from .support import ClaimSupportEngine, ClaimSupportRater, FakeClaimSupportRater, SupportAiOutput

__all__ = [
    "ClaimService",
    "CandidateService",
    "ClaimSupportEngine",
    "ClaimSupportRater",
    "FakeClaimSupportRater",
    "SupportAiOutput",
    "DecisionService",
]
