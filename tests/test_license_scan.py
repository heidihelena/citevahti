"""Source reuse rights (oa_status/license) from OpenAlex — REPORTS, never DECIDES.

Offline: a fake HttpClient stands in for OpenAlex, and a fake client drives the
candidate scan. We assert the data is captured and surfaced, and that unknown/closed
never becomes a false 'reusable'."""

from __future__ import annotations

from citevahti.claims import CandidateService, ClaimService
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.openalex import OpenAlexClient
from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore
from citevahti.tools import scan_licenses


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


def _pin(cfg):
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    cfg.ai_provenance.prompt_template_version = "v1"
    return cfg


def _ledger_with_candidate(tmp_path, *, doi="10.1056/NEJMoa1102873"):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider([ProviderHit(pmid="21714641", doi=doi, title="NLST")]),
                          library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    return store, claim.claim_id


# ---- OpenAlex client: extraction + honest unknowns -------------------------
class _FakeHttp:
    def __init__(self, *, payload=None, status=200, raise_exc=None):
        self._payload, self._status, self._raise = payload, status, raise_exc

    def get(self, url, headers=None, params=None):
        if self._raise:
            raise self._raise
        return HttpResponse(status_code=self._status, _json=self._payload)


def test_openalex_licensing_extracts_oa_and_license():
    http = _FakeHttp(payload={"open_access": {"oa_status": "gold", "is_oa": True},
                              "best_oa_location": {"license": "cc-by"}})
    r = OpenAlexClient(http=http).licensing(doi="10.1/x")
    assert r == {"oa_status": "gold", "is_oa": True, "license": "cc-by"}


def test_openalex_licensing_closed_work_has_no_license():
    http = _FakeHttp(payload={"open_access": {"oa_status": "closed", "is_oa": False},
                              "best_oa_location": None})
    r = OpenAlexClient(http=http).licensing(doi="10.1/x")
    assert r["oa_status"] == "closed" and r["license"] is None


def test_openalex_licensing_unknown_when_offline_or_missing():
    assert OpenAlexClient(http=_FakeHttp(raise_exc=ProbeTransportError("down"))).licensing(doi="10.1/x") is None
    assert OpenAlexClient(http=_FakeHttp(status=404)).licensing(doi="10.1/x") is None
    assert OpenAlexClient(http=_FakeHttp(payload={})).licensing() is None  # no doi/pmid


# ---- the candidate scan fills the fields + audits --------------------------
class _FakeOA:
    def __init__(self, rights):
        self._rights = rights

    def licensing(self, *, doi=None, pmid=None):
        return self._rights


def test_scan_fills_candidate_reuse_rights(tmp_path):
    store, claim_id = _ledger_with_candidate(tmp_path)
    client = _FakeOA({"oa_status": "gold", "is_oa": True, "license": "cc-by"})
    rep = scan_licenses(root=str(tmp_path), client=client)
    assert rep == {"filled": 1, "checked": 1}
    cand = store.load_candidates(claim_id).candidates[0]
    assert cand.oa_status == "gold" and cand.license == "cc-by"


def test_scan_leaves_fields_unset_when_unknown(tmp_path):
    # OpenAlex returns nothing usable → never a false 'closed'/'reusable', fields stay None
    store, claim_id = _ledger_with_candidate(tmp_path)
    rep = scan_licenses(root=str(tmp_path), client=_FakeOA(None))
    assert rep["filled"] == 0
    cand = store.load_candidates(claim_id).candidates[0]
    assert cand.oa_status is None and cand.license is None


def test_scan_is_audited(tmp_path):
    store, _ = _ledger_with_candidate(tmp_path)
    scan_licenses(root=str(tmp_path), client=_FakeOA({"oa_status": "closed", "license": None}))
    assert "license.scan" in [e.event for e in store.audit.entries()]
