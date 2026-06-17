"""Claims: the first-class spine of the evidence-decision ledger (ADR-0001)."""

from .candidates import CandidateService
from .decisions import DecisionService
from .service import ClaimService
from .support import ClaimSupportEngine, ClaimSupportRater, FakeClaimSupportRater, SupportAiOutput
from .ai import HttpClaimSupportRater, build_support_ai_rater

__all__ = [
    "ClaimService",
    "CandidateService",
    "ClaimSupportEngine",
    "ClaimSupportRater",
    "FakeClaimSupportRater",
    "SupportAiOutput",
    "HttpClaimSupportRater",
    "build_support_ai_rater",
    "DecisionService",
]
