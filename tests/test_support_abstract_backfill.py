"""The AI second opinion abstains when a candidate has only a title — so before an
AI support run, CiteVahti backfills a missing abstract from PubMed (best-effort).
"""

from citevahti import tools
from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    FakeClaimSupportRater,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore


class _Provider:                       # stages a candidate with a PMID but NO abstract
    name = "pubmed"

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(
            status="ok", count=1, email_present=True, rate_tier="3rps",
            hits=[ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873", title="NLST")])


class _FetchProvider:                  # the PubMed provider used for the on-demand backfill
    def fetch_records(self, ids, include_abstracts=False):
        return [ProviderHit(pmid="21714641", title="NLST",
                            abstract="LDCT screening cut lung-cancer mortality by 20% in NLST.")]


def _pin(cfg):
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    cfg.ai_provenance.prompt_template_version = "v1"
    return cfg


def test_support_run_ai_backfills_a_missing_abstract(tmp_path, monkeypatch):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(),
                          library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    assert store.load_candidates(claim.claim_id).candidates[0].abstract is None   # title-only

    rec = ClaimSupportEngine(store).support_start(claim.claim_id, cand_id)
    # _backfill_abstract now lives in tools.support (ADR-0010 PR 1g) and resolves
    # _pubmed_provider in that module's namespace — patch it where it is looked up.
    monkeypatch.setattr(tools.support, "_pubmed_provider", lambda root, http=None: _FetchProvider())
    tools.support_run_ai(rec.rating_id, root=str(tmp_path),
                         rater=FakeClaimSupportRater(value="directly_supports"))

    cand = store.load_candidates(claim.claim_id).candidates[0]
    assert cand.abstract and "NLST" in cand.abstract        # backfilled, and saved to the ledger
