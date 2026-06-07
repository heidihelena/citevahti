"""Semantic Scholar search (another API-backed source, like OpenAlex).

Free Graph API, broad coverage, returns DOIs + PMIDs. No key required (an optional
``x-api-key`` raises the rate limit). Normalized to the same hit shape the panel's
intake CSV expects, so it links identically to PubMed / OpenAlex / Zotero results.
"""

from __future__ import annotations

from typing import Optional

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "title,year,venue,externalIds,authors"


class SemanticScholarClient:
    def __init__(self, http=None, *, api_key: Optional[str] = None) -> None:
        self._http = http
        self.api_key = api_key

    def _client(self):
        if self._http is not None:
            return self._http
        from .probe.client import HttpxClient
        return HttpxClient(timeout=8.0)

    @staticmethod
    def _normalize(p: dict) -> dict:
        ext = p.get("externalIds") or {}
        return {
            "title": p.get("title"),
            "doi": ext.get("DOI"),
            "pmid": str(ext["PubMed"]) if ext.get("PubMed") else None,
            "year": p.get("year"),
            "journal": p.get("venue"),
            "authors": [a.get("name") for a in (p.get("authors") or []) if a.get("name")],
        }

    def search(self, query: str, max_results: int = 15) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        headers = {"x-api-key": self.api_key} if self.api_key else None
        from .probe.client import ProbeTransportError
        try:
            resp = self._client().get(SEARCH_URL, params={"query": query, "limit": max_results,
                                                          "fields": _FIELDS}, headers=headers)
        except ProbeTransportError:
            return []
        if resp.status_code != 200:
            return []
        try:
            data = resp.json().get("data") or []
        except Exception:  # noqa: BLE001
            return []
        return [self._normalize(p) for p in data]
