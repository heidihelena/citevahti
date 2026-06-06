"""ClaimCheckService: per-citekey + aggregate lexical support detection."""

from __future__ import annotations

from typing import Optional

from .. import __version__
from ..retrieval.service import PassageRetrievalService
from ..retrieval.source import TextSource
from ..schemas.claimcheck import ClaimCheckResult, ClaimStatus, PerCitekeyResult
from ..schemas.common import Provenance
from ..util import config_hash, utc_now_iso

# Minimum fraction of the claim's content tokens that must appear in a passage
# for it to count as a *candidate* (still not an assertion of truth).
_SUPPORT_THRESHOLD = 0.5
_MAX_PASSAGES = 3


class ClaimCheckService:
    def __init__(self, source: TextSource) -> None:
        self.source = source
        self.retrieval = PassageRetrievalService(source)

    def _provenance(self, claim_text, citekeys) -> Provenance:
        return Provenance(
            tool="claim_check", tool_version=__version__, ran_at=utc_now_iso(),
            config_hash=config_hash({"claim": claim_text, "citekeys": list(citekeys)}),
            sources=[{"kind": "zotero_api", "detail": "fulltext + annotations (read-only)"},
                     {"kind": "bbt", "detail": "exact citekey resolution"}],
        )

    def _check_one(self, claim_text: str, citekey: str, require_page: bool,
                   library: str) -> PerCitekeyResult:
        retr = self.retrieval.retrieve(citekey=citekey, query=claim_text,
                                        max_passages=_MAX_PASSAGES, library=library)
        if retr.status == "degraded":
            # unresolved citekey / no source text -> cannot verify (never fabricate)
            return PerCitekeyResult(citekey=citekey, status="unverifiable",
                                    zotero_key=retr.zotero_key, reason=retr.error_code)

        candidates = [p for p in retr.passages if (p.score or 0) >= _SUPPORT_THRESHOLD]
        if require_page:
            paged = [p for p in candidates if p.page is not None]
            if not paged:
                # required locator/page unavailable -> unverifiable
                return PerCitekeyResult(citekey=citekey, status="unverifiable",
                                        zotero_key=retr.zotero_key,
                                        reason="page/locator required but unavailable")
            candidates = paged

        if candidates:
            best = max(p.score or 0 for p in candidates)
            return PerCitekeyResult(citekey=citekey, status="supported_candidate",
                                    zotero_key=retr.zotero_key, score=best, passages=candidates)
        # source available + searched, but no adequate support
        return PerCitekeyResult(citekey=citekey, status="no_support_found",
                                zotero_key=retr.zotero_key)

    @staticmethod
    def _aggregate(statuses: list[ClaimStatus]) -> ClaimStatus:
        if "supported_candidate" in statuses:
            return "supported_candidate"
        if "no_support_found" in statuses:
            return "no_support_found"
        return "unverifiable"

    def check(self, claim_text: str, citekeys: list[str], context: Optional[str] = None,
              require_page: bool = False, library="personal") -> ClaimCheckResult:
        prov = self._provenance(claim_text, citekeys)
        per = [self._check_one(claim_text, ck, require_page, library) for ck in citekeys]
        result = ClaimCheckResult(
            claim_text=claim_text, require_page=require_page, per_citekey=per,
            aggregate_status=self._aggregate([p.status for p in per]) if per else "unverifiable",
            provenance=prov)
        if not citekeys:
            result.warnings.append("no citekeys provided")
        return result
