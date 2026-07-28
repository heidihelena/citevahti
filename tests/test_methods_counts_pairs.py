"""The published methods numbers count judged PAIRS, never rating files.

`support_start` mints a fresh rating id on every call, so one (claim, candidate) pair can
carry several claim-support records on disk — a real prescreen ledger held 118 records for
61 pairs. The evidence-basis sentence and the PRISMA 'assessed' box both speak of *pairs*,
so counting files put "118 rated claim–candidate pair(s)" into published prose and made the
PRISMA flow report more pairs assessed than were ever staged. Counting merely-opened records
would be wrong the other way: a sealed, unrated record is not an assessment.
"""

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    FakeClaimSupportRater,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.report.methods import _basis_line, _basis_stats, _prisma_flow, _prisma_table
from citevahti.state import CiteVahtiStore


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


def _setup(tmp_path):
    """One claim, one candidate — so 'pairs' is unambiguously 1 however many records exist."""
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(
        [ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873", title="NLST")]),
        library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return store, claim.claim_id, cand_id


def test_duplicate_records_for_one_pair_are_counted_once(tmp_path):
    """The churn case from the real ledger: several records, one pair, one rating."""
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    for _ in range(4):
        # force_new because a plain start is idempotent now; these stand in for the open
        # slots a concurrent panel leaves, and for every pre-existing ledger's duplicates.
        eng.support_start(claim_id, cand_id, force_new=True)

    assert len(store.list_support_ratings()) == 5   # five files on disk...
    assert _basis_stats(store)["rated"] == 1        # ...one judged pair
    assert _prisma_flow(store)["assessed"] == 1
    assert "Of 1 rated claim–candidate pair(s)" in _basis_line(store)


def test_an_opened_but_unrated_pair_is_not_assessed(tmp_path):
    """`support_start` seals an empty record. Nobody has judged anything yet, so the
    evidence-basis line stays silent and the PRISMA 'assessed' box stays at zero."""
    store, claim_id, cand_id = _setup(tmp_path)
    ClaimSupportEngine(store).support_start(claim_id, cand_id)

    assert store.list_support_ratings()                 # a record exists...
    assert _basis_stats(store)["rated"] == 0            # ...but nothing was assessed
    assert _prisma_flow(store)["assessed"] == 0
    assert _basis_line(store) == ""


def test_prisma_flow_never_assesses_more_pairs_than_were_staged(tmp_path):
    """The flow must stay monotone. Counting rating files reported 118 pairs assessed against
    61 ever staged — an impossible funnel in a figure meant for publication."""
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    for _ in range(9):
        eng.support_start(claim_id, cand_id, force_new=True)

    f = _prisma_flow(store)
    assert f["staged"] == 1
    assert f["staged"] >= f["assessed"] >= f["included"]
    assert "| Claim–evidence pairs assessed (human-rated) | 1 |" in _prisma_table(store)


def test_assessed_counts_human_ratings_not_ai_only_pairs(tmp_path):
    """The PRISMA row says 'human-rated'. An AI second opinion is not a human assessment, so
    an AI-only pair must not enter that box — while the evidence-basis line, which describes
    how support was assessed at all, does count it."""
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="directly_supports"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_run_ai(rec.rating_id)

    assert _prisma_flow(store)["assessed"] == 0     # no human has rated this pair
    assert _basis_stats(store)["rated"] == 1        # but it was assessed by the AI rater
