"""PubMed search diagnostics: total count, query translation, warnings/errors.

Regression for the medical-librarian finding: a malformed query (`lung cancer
AND (`) returned `ok` and staged unrelated results, and there was no total
count or query-translation capture. The exact query is still preserved.
"""

from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.pubmed import PubMedProvider, RateLimiter
from citevahti.pubmed.provider import _parse_esearch

EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle><MedlineCitation><PMID>111</PMID>
  <Article><ArticleTitle>T</ArticleTitle>
   <Journal><Title>J</Title><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
  </Article></MedlineCitation>
  <PubmedData><ArticleIdList><ArticleId IdType="pubmed">111</ArticleId></ArticleIdList></PubmedData>
 </PubmedArticle>
</PubmedArticleSet>"""


class SeqClient:
    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}

    def get(self, url, headers=None, params=None):
        for frag, q in self.routes.items():
            if frag in url:
                r = q.pop(0) if len(q) > 1 else q[0]
                if isinstance(r, Exception):
                    raise r
                return r
        raise ProbeTransportError(f"no route for {url}")

    def post(self, url, json=None, headers=None):
        return self.get(url)


def _provider(esearch, efetch=EFETCH_XML):
    client = SeqClient({"esearch": [HttpResponse(200, _json=esearch)],
                        "efetch": [HttpResponse(200, text=efetch)]})
    return PubMedProvider(client, "me@example.com", None,
                          rate_limiter=RateLimiter(1000, sleep=lambda *_: None),
                          sleep=lambda *_: None)


# ---- _parse_esearch ---------------------------------------------------------
def test_parses_total_count_and_query_translation():
    body = {"esearchresult": {"idlist": ["1", "2"], "count": "4137",
                              "querytranslation": '"lung neoplasms"[MeSH]'}}
    es = _parse_esearch(body)
    assert es.idlist == ["1", "2"]
    assert es.total == 4137                    # the TRUE total, not len(idlist)
    assert es.query_translation == '"lung neoplasms"[MeSH]'
    assert es.warnings == [] and es.errors == []


def test_captures_warninglist_and_errorlist():
    body = {"esearchresult": {
        "idlist": ["1"], "count": "1",
        "warninglist": {"phrasesignored": [], "quotedphrasesnotfound": [],
                        "outputmessages": ["Unbalanced quotes or parentheses; ignored."]},
        "errorlist": {"phrasesnotfound": ["zzqq"], "fieldsnotfound": []}}}
    es = _parse_esearch(body)
    assert any("Unbalanced" in w for w in es.warnings)
    assert any("zzqq" in e for e in es.errors)


def test_top_level_error_is_an_error():
    es = _parse_esearch({"esearchresult": {"ERROR": "Can't run executor", "idlist": []}})
    assert es.errors and es.idlist == []


# ---- provider.search status ------------------------------------------------
def test_clean_search_is_ok_with_total():
    res = _provider({"esearchresult": {"idlist": ["111"], "count": "57"}}).search("lung cancer")
    assert res.status == "ok"
    assert res.count == 1 and res.total_count == 57       # returned vs matched
    assert len(res.hits) == 1


def test_warnings_still_stage_but_flagged():
    res = _provider({"esearchresult": {
        "idlist": ["111"], "count": "1",
        "warninglist": {"outputmessages": ["Unbalanced quotes or parentheses."]}}}).search("x AND (")
    assert res.status == "warnings"                       # not a clean ok
    assert res.hits and any("Unbalanced" in w for w in res.warnings)


def test_query_error_with_no_results_degrades_not_ok():
    res = _provider({"esearchresult": {"ERROR": "bad query", "idlist": []}}).search("AND (")
    assert res.status == "pubmed_query_error"
    assert res.hits == [] and res.remediation                 # never stage broad unintended hits
