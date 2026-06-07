"""CrossRef title → DOI resolution (strict).

For candidates that have neither a PMID nor a DOI (manual / Zotero-library imports),
we can look up the DOI from CrossRef by title. For a citation-integrity tool a
*wrong* DOI is worse than none, so this is deliberately conservative: a candidate
is only accepted when the returned title is a near-exact normalized match to the
query title (default ratio ≥ 0.92). On any miss/ambiguity it returns ``None``.

CrossRef has no key; we pass ``mailto`` (the onboarded NCBI email) to use the polite
pool. Note: CrossRef also carries the Retraction Watch dataset, so this same client
can later back a real retraction check (DOI-based).
"""

from __future__ import annotations

import difflib
import re
from typing import Optional

WORKS_URL = "https://api.crossref.org/works"


def _norm(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


class CrossrefClient:
    def __init__(self, http=None, *, mailto: Optional[str] = None, min_similarity: float = 0.92) -> None:
        self._http = http
        self.mailto = mailto
        self.min_similarity = min_similarity

    def _client(self):
        if self._http is not None:
            return self._http
        from .probe.client import HttpxClient
        return HttpxClient(timeout=8.0)

    def doi_for_title(self, title: str) -> Optional[str]:
        """Best DOI for ``title`` — only if the match is strong enough to trust."""
        title = (title or "").strip()
        if not title:
            return None
        params = {"query.bibliographic": title, "rows": 3, "select": "DOI,title"}
        if self.mailto:
            params["mailto"] = self.mailto
        from .probe.client import ProbeTransportError
        try:
            resp = self._client().get(WORKS_URL, params=params)
        except ProbeTransportError:
            return None
        if resp.status_code != 200:
            return None
        try:
            items = (resp.json().get("message") or {}).get("items") or []
        except Exception:  # noqa: BLE001
            return None
        want = _norm(title)
        best_doi, best_ratio = None, 0.0
        for it in items:
            cand_title = (it.get("title") or [""])
            cand_title = cand_title[0] if cand_title else ""
            ratio = difflib.SequenceMatcher(None, want, _norm(cand_title)).ratio()
            if ratio > best_ratio:
                best_ratio, best_doi = ratio, it.get("DOI")
        return best_doi if best_ratio >= self.min_similarity else None
