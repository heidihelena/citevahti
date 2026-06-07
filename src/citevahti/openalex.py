"""OpenAlex search + retraction status.

OpenAlex is the practical, API-backed alternative to Google Scholar for broad
coverage (beyond PubMed: preprints, books, non-medical) — it has a free REST API,
returns DOIs/PMIDs, and exposes an ``is_retracted`` flag. So ONE client powers both
the panel's "find evidence" (extra source) and the retraction check. No key; we pass
``mailto`` (the onboarded NCBI email) for the polite pool.
"""

from __future__ import annotations

from typing import Optional

WORKS_URL = "https://api.openalex.org/works"
_SELECT = "id,doi,title,publication_year,ids,primary_location,authorships,is_retracted"


def _strip_doi(doi: Optional[str]) -> Optional[str]:
    return doi.replace("https://doi.org/", "") if doi else None


def _strip_pmid(pmid: Optional[str]) -> Optional[str]:
    return pmid.rstrip("/").split("/")[-1] if pmid else None


class OpenAlexClient:
    def __init__(self, http=None, *, mailto: Optional[str] = None) -> None:
        self._http = http
        self.mailto = mailto

    def _client(self):
        if self._http is not None:
            return self._http
        from .probe.client import HttpxClient
        return HttpxClient(timeout=8.0)

    def _params(self, extra: dict) -> dict:
        p = dict(extra)
        if self.mailto:
            p["mailto"] = self.mailto
        return p

    @staticmethod
    def _normalize(w: dict) -> dict:
        ids = w.get("ids") or {}
        journal = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
        authors = [(a.get("author") or {}).get("display_name")
                   for a in (w.get("authorships") or [])]
        return {
            "title": w.get("title"),
            "doi": _strip_doi(w.get("doi")),
            "pmid": _strip_pmid(ids.get("pmid")),
            "year": w.get("publication_year"),
            "journal": journal,
            "authors": [a for a in authors if a],
            "is_retracted": bool(w.get("is_retracted")),
        }

    def search(self, query: str, max_results: int = 15) -> list[dict]:
        """Normalized hits ({title, doi, pmid, year, journal, authors, is_retracted})."""
        query = (query or "").strip()
        if not query:
            return []
        from .probe.client import ProbeTransportError
        try:
            resp = self._client().get(WORKS_URL, params=self._params(
                {"search": query, "per_page": max_results, "select": _SELECT}))
        except ProbeTransportError:
            return []
        if resp.status_code != 200:
            return []
        try:
            results = resp.json().get("results") or []
        except Exception:  # noqa: BLE001
            return []
        return [self._normalize(w) for w in results]

    def is_retracted(self, *, doi: Optional[str] = None, pmid: Optional[str] = None) -> Optional[bool]:
        """Retraction status for a DOI or PMID via OpenAlex. ``None`` if unknown
        (not found / offline) — never a false 'not retracted'."""
        ident = f"https://doi.org/{doi}" if doi else (f"pmid:{pmid}" if pmid else None)
        if not ident:
            return None
        from .probe.client import ProbeTransportError
        try:
            resp = self._client().get(f"{WORKS_URL}/{ident}",
                                      params=self._params({"select": "is_retracted"}))
        except ProbeTransportError:
            return None
        if resp.status_code != 200:
            return None
        try:
            return bool(resp.json().get("is_retracted"))
        except Exception:  # noqa: BLE001
            return None
