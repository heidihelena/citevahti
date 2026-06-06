"""LiteratureProvider interface + PubMedProvider (NCBI E-utilities)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, runtime_checkable

from ..probe.client import HttpClient, ProbeTransportError
from .parse import parse_efetch_xml

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedUnavailable(Exception):
    code = "pubmed_unavailable"


@dataclass
class ProviderHit:
    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: str = ""
    authors: list[str] = field(default_factory=list)
    journal: Optional[str] = None
    publication_date: Optional[str] = None
    year: Optional[int] = None
    abstract: Optional[str] = None


@dataclass
class _EsearchResult:
    idlist: list[str] = field(default_factory=list)
    total: int = 0                       # esearchresult.count (true total in PubMed)
    query_translation: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ProviderSearchResult:
    status: str = "ok"   # ok | warnings | missing_ncbi_email | pubmed_unavailable | pubmed_query_error
    hits: list[ProviderHit] = field(default_factory=list)
    count: int = 0                       # records RETURNED (<= retmax)
    total_count: int = 0                 # records MATCHED in PubMed (the true total)
    query: str = ""
    query_translation: Optional[str] = None   # how NCBI parsed the query
    rate_tier: str = "3rps"
    email_present: bool = False
    api_key_present: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    remediation: Optional[str] = None
    error: Optional[str] = None


@runtime_checkable
class LiteratureProvider(Protocol):
    name: str

    def search(self, query: str, max_results: int = 20,
               date_range: Optional[dict] = None,
               include_abstracts: bool = False) -> ProviderSearchResult: ...


class RateLimiter:
    """Token-bucket-ish limiter honoring requests/second."""

    def __init__(self, rps: float, sleep: Callable[[float], None] = time.sleep) -> None:
        self.min_interval = 1.0 / rps if rps > 0 else 0.0
        self._sleep = sleep
        self._last = 0.0

    def acquire(self) -> None:
        now = time.monotonic()
        wait = self._last + self.min_interval - now
        if wait > 0:
            self._sleep(wait)
        self._last = time.monotonic()


class PubMedProvider:
    name = "pubmed"

    def __init__(self, http: HttpClient, email: Optional[str], api_key: Optional[str] = None,
                 rate_limiter: Optional[RateLimiter] = None, max_retries: int = 3,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.http = http
        self.email = email
        self.api_key = api_key
        self.rate_tier = "10rps" if api_key else "3rps"
        self.limiter = rate_limiter or RateLimiter(10 if api_key else 3, sleep=sleep)
        self.max_retries = max_retries
        self._sleep = sleep

    # ---- low-level -------------------------------------------------------
    def _params(self, extra: dict) -> dict:
        params = {"email": self.email or "", "tool": "citevahti"}
        if self.api_key:
            params["api_key"] = self.api_key
        params.update(extra)
        return params

    def _get(self, path: str, params: dict):
        url = f"{EUTILS_BASE}/{path}"
        last_err = "unknown"
        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()
            try:
                resp = self.http.get(url, params=self._params(params))
            except ProbeTransportError as exc:
                last_err = str(exc)
            else:
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    last_err = f"HTTP {resp.status_code}"
                else:
                    raise PubMedUnavailable(f"HTTP {resp.status_code}")
            if attempt < self.max_retries:
                self._sleep(0.2 * (2 ** attempt))  # exponential backoff
        raise PubMedUnavailable(last_err)

    def _esearch(self, query: str, max_results: int, date_range: Optional[dict]) -> list[str]:
        params = {"db": "pubmed", "term": query, "retmax": str(max_results), "retmode": "json"}
        if date_range:
            if date_range.get("from"):
                params["mindate"] = date_range["from"]
            if date_range.get("to"):
                params["maxdate"] = date_range["to"]
            if "mindate" in params or "maxdate" in params:
                params["datetype"] = "pdat"
        resp = self._get("esearch.fcgi", params)
        try:
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise PubMedUnavailable(f"esearch: bad JSON ({exc})") from exc
        return _parse_esearch(body)

    def _efetch(self, pmids: list[str], include_abstracts: bool) -> list[ProviderHit]:
        resp = self._get("efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids),
                                         "retmode": "xml", "rettype": "abstract"})
        hits = []
        for d in parse_efetch_xml(resp.text):
            if not include_abstracts:
                d["abstract"] = None
            hits.append(ProviderHit(**d))
        return hits

    # ---- public ----------------------------------------------------------
    def search(self, query: str, max_results: int = 20, date_range: Optional[dict] = None,
               include_abstracts: bool = False) -> ProviderSearchResult:
        base = ProviderSearchResult(query=query, rate_tier=self.rate_tier,
                                    email_present=bool(self.email),
                                    api_key_present=bool(self.api_key))
        if not self.email:
            base.status = "missing_ncbi_email"
            base.remediation = ("Set NCBI_EMAIL to run live PubMed queries (required by NCBI "
                                "E-utilities). NCBI_API_KEY is optional and raises the rate limit.")
            return base
        try:
            es = self._esearch(query, max_results, date_range)
            base.count = len(es.idlist)
            base.total_count = es.total
            base.query_translation = es.query_translation
            base.warnings = es.warnings
            base.errors = es.errors
            # A query error with no results is honest degradation -- never stage broad,
            # unintended hits as if the query were valid.
            if es.errors and not es.idlist:
                base.status = "pubmed_query_error"
                base.error = "; ".join(es.errors)
                base.remediation = ("PubMed reported a query problem (often unbalanced "
                                    "quotes/parentheses or an unknown field tag). The exact query "
                                    "was preserved; fix it and re-run.")
                return base
            if es.idlist:
                base.hits = self._efetch(es.idlist, include_abstracts)
            if es.warnings or es.errors:
                base.status = "warnings"
        except PubMedUnavailable as exc:
            base.status = "pubmed_unavailable"
            base.error = str(exc)
            base.remediation = "PubMed/E-utilities is unreachable or rate-limited; try again later."
            base.hits = []
            return base
        return base


def _parse_esearch(body: dict) -> _EsearchResult:
    """Extract idlist + total count + query translation + warnings/errors.

    NCBI reports trouble three ways: a top-level ``ERROR`` string, an
    ``errorlist`` (phrasesnotfound / fieldnotfound), and a ``warninglist``
    (phrasesignored / quotedphrasesnotfound / outputmessages). All are surfaced
    so a malformed query is never silently treated as a clean search.
    """
    er = (body or {}).get("esearchresult") or {}
    out = _EsearchResult(
        idlist=list(er.get("idlist") or []),
        query_translation=er.get("querytranslation") or None)
    try:
        out.total = int(er.get("count"))
    except (TypeError, ValueError):
        out.total = len(out.idlist)

    if er.get("ERROR"):
        out.errors.append(str(er["ERROR"]))
    el = er.get("errorlist") or {}
    for kind in ("phrasesnotfound", "fieldnotfound", "fieldsnotfound"):
        for v in el.get(kind) or []:
            out.errors.append(f"{kind}: {v}")
    wl = er.get("warninglist") or {}
    for kind in ("phrasesignored", "quotedphrasesnotfound", "outputmessages"):
        for v in wl.get(kind) or []:
            out.warnings.append(f"{kind}: {v}")
    return out
