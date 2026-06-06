"""PubMed provider: parsing, abstract gating, degradation, retry -- no live net."""

from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.pubmed import PubMedProvider, RateLimiter

ESEARCH = {"esearchresult": {"idlist": ["111"], "count": "1"}}
EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle>
  <MedlineCitation>
   <PMID>111</PMID>
   <Article>
    <ArticleTitle>Effect of X on Y</ArticleTitle>
    <Journal><Title>J Test</Title>
     <JournalIssue><PubDate><Year>2020</Year><Month>Mar</Month></PubDate></JournalIssue></Journal>
    <AuthorList><Author><LastName>Smith</LastName><ForeName>Jane</ForeName></Author></AuthorList>
    <Abstract><AbstractText>Background results here.</AbstractText></Abstract>
   </Article>
  </MedlineCitation>
  <PubmedData><ArticleIdList>
    <ArticleId IdType="pubmed">111</ArticleId>
    <ArticleId IdType="doi">10.1/ABC</ArticleId>
  </ArticleIdList></PubmedData>
 </PubmedArticle>
</PubmedArticleSet>"""


class SeqClient:
    """Returns queued responses per URL fragment (last response repeats)."""

    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.calls = []

    def get(self, url, headers=None, params=None):
        self.calls.append(url)
        for frag, q in self.routes.items():
            if frag in url:
                r = q.pop(0) if len(q) > 1 else q[0]
                if isinstance(r, Exception):
                    raise r
                return r
        raise ProbeTransportError(f"no route for {url}")

    def post(self, url, json=None, headers=None):
        return self.get(url)


def _client(esearch=ESEARCH, efetch=EFETCH_XML):
    return SeqClient({"esearch": [HttpResponse(200, _json=esearch)],
                      "efetch": [HttpResponse(200, text=efetch)]})


def _provider(client, email="me@example.com", api_key=None):
    return PubMedProvider(client, email, api_key,
                          rate_limiter=RateLimiter(1000, sleep=lambda *_: None),
                          sleep=lambda *_: None)


def test_parses_esearch_and_efetch():
    r = _provider(_client()).search("cancer", max_results=5)
    assert r.status == "ok" and r.count == 1 and len(r.hits) == 1
    h = r.hits[0]
    assert h.title == "Effect of X on Y" and h.journal == "J Test" and h.year == 2020
    assert h.authors == ["Jane Smith"]


def test_extracts_doi_and_pmid():
    h = _provider(_client()).search("cancer").hits[0]
    assert h.pmid == "111" and h.doi == "10.1/ABC"


def test_abstract_only_when_requested():
    no_ab = _provider(_client()).search("cancer", include_abstracts=False).hits[0]
    with_ab = _provider(_client()).search("cancer", include_abstracts=True).hits[0]
    assert no_ab.abstract is None
    assert with_ab.abstract and "Background results" in with_ab.abstract


def test_missing_email_degrades_honestly():
    client = _client()
    r = _provider(client, email=None).search("cancer")
    assert r.status == "missing_ncbi_email" and r.hits == []
    assert r.remediation and "NCBI_EMAIL" in r.remediation
    assert client.calls == []  # no network attempted


def test_rate_tier_depends_on_api_key():
    assert _provider(_client(), api_key=None).rate_tier == "3rps"
    assert _provider(_client(), api_key="k").rate_tier == "10rps"


def test_429_retry_then_success():
    client = SeqClient({
        "esearch": [HttpResponse(429, text="slow down"), HttpResponse(200, _json=ESEARCH)],
        "efetch": [HttpResponse(200, text=EFETCH_XML)],
    })
    r = _provider(client).search("cancer")
    assert r.status == "ok" and len(r.hits) == 1
    assert sum("esearch" in c for c in client.calls) == 2  # retried once


def test_persistent_5xx_degrades():
    client = SeqClient({"esearch": [HttpResponse(503, text="down")]})
    r = _provider(client).search("cancer")
    assert r.status == "pubmed_unavailable" and r.hits == []


# --- regression: DOI must come from the article's own id list, not its references ---
EFETCH_WITH_REFERENCES = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle>
  <MedlineCitation>
   <PMID>40990985</PMID>
   <Article>
    <ArticleTitle>Real article about lung cancer.</ArticleTitle>
    <Journal><Title>European radiology</Title>
     <JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal>
    <AuthorList><Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author></AuthorList>
    <Abstract><AbstractText>Body.</AbstractText></Abstract>
   </Article>
  </MedlineCitation>
  <PubmedData>
   <ArticleIdList>
    <ArticleId IdType="pubmed">40990985</ArticleId>
    <ArticleId IdType="doi">10.1007/s00330-025-12015-z</ArticleId>
   </ArticleIdList>
   <ReferenceList>
    <Reference><Citation>Cited ref one</Citation>
     <ArticleIdList>
      <ArticleId IdType="pubmed">99999</ArticleId>
      <ArticleId IdType="doi">10.1016/j.acra.2020.05.044</ArticleId>
     </ArticleIdList></Reference>
    <Reference><Citation>Cited ref two</Citation>
     <ArticleIdList><ArticleId IdType="doi">10.9999/another-reference</ArticleId></ArticleIdList>
    </Reference>
   </ReferenceList>
  </PubmedData>
 </PubmedArticle>
</PubmedArticleSet>"""


def test_doi_is_article_own_not_reference():
    from citevahti.pubmed.parse import parse_efetch_xml
    hits = parse_efetch_xml(EFETCH_WITH_REFERENCES)
    assert len(hits) == 1
    h = hits[0]
    # the article's own DOI/PMID, never a cited reference's
    assert h["doi"] == "10.1007/s00330-025-12015-z"
    assert h["pmid"] == "40990985"
    assert h["doi"] != "10.1016/j.acra.2020.05.044"
