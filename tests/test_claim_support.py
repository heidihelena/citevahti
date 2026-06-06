"""Claim-support dual rating (ADR-0001 step 3): the core asset, invariants held.

Mirrors the study-quality engine's guarantees on the (claim, candidate) support
dimension: human value locked, AI blind/advisory/never-final, discordance needs
human adjudication, final never sourced from AI. Plus the support vocabulary and
PICO fit subscores. Fully offline (Fake rater).
"""

import pytest

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    FakeClaimSupportRater,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.schemas.claim_support import FitScores
from citevahti.state import CiteVahtiStore
from citevahti.validators.claim_support import ClaimSupportError
from citevahti.validators.errors import (
    HumanValueLockedError,
    ModelNotPinnedError,
    TaskNotAllowedError,
)


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


def _setup(tmp_path, pin_model=False):
    store = CiteVahtiStore(tmp_path)
    store.init()
    if pin_model:
        store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(
        [ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873", title="NLST")]),
        library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return store, claim.claim_id, cand_id


# ---- start -----------------------------------------------------------------
def test_start_ties_rating_to_claim_and_candidate(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rec = ClaimSupportEngine(store).support_start(claim_id, cand_id)
    assert rec.claim_id == claim_id and rec.candidate_id == cand_id
    assert rec.rating_id.startswith("cs-")
    assert rec.blinding.access_log[0].event == "seal"


def test_start_rejects_candidate_not_linked(tmp_path):
    store, claim_id, _cand_id = _setup(tmp_path)
    with pytest.raises(ClaimSupportError):
        ClaimSupportEngine(store).support_start(claim_id, "cand-not-linked")


# ---- human commit + lock ---------------------------------------------------
def test_commit_human_locks_value_and_fit(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    rec = eng.support_commit_human(
        rec.rating_id, "directly_supports",
        fit=FitScores(population_fit=2, intervention_fit=2, outcome_fit=2, claim_fit=2),
        rationale="primary endpoint matches the claim", committed_by="researcher")
    assert rec.human_rating.value == "directly_supports" and rec.human_rating.locked
    assert rec.human_rating.fit.claim_fit == 2


def test_locked_human_value_cannot_be_overwritten(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    with pytest.raises(ClaimSupportError):
        eng.support_commit_human(rec.rating_id, "does_not_support")


def test_store_guards_human_overwrite_on_resave(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    rec = eng.support_commit_human(rec.rating_id, "partially_supports")
    rec.human_rating.value = "contradicts"           # tamper
    with pytest.raises(HumanValueLockedError):
        store.save_support_rating(rec)


def test_bad_support_value_rejected(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    with pytest.raises(ClaimSupportError):
        eng.support_commit_human(rec.rating_id, "totally_supports")


def test_bad_fit_score_rejected(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rec = ClaimSupportEngine(store).support_start(claim_id, cand_id)
    with pytest.raises(ClaimSupportError):
        ClaimSupportEngine(store).support_commit_human(
            rec.rating_id, "unclear", fit=FitScores(claim_fit=3))


# ---- AI run (blind, advisory, pinned) --------------------------------------
def test_ai_run_requires_pinned_model(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, pin_model=False)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="directly_supports"))
    rec = eng.support_start(claim_id, cand_id)
    with pytest.raises(ModelNotPinnedError):
        eng.support_run_ai(rec.rating_id)


def test_ai_run_rejects_unallowed_task(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, pin_model=True)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="directly_supports"))
    rec = eng.support_start(claim_id, cand_id)
    with pytest.raises(TaskNotAllowedError):
        eng.support_run_ai(rec.rating_id, task_type="claim_check")


def test_ai_run_records_advisory_rating_with_provenance(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, pin_model=True)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(
        value="partially_supports", confidence=0.7,
        fit=FitScores(population_fit=1, claim_fit=1)))
    rec = eng.support_start(claim_id, cand_id)
    rec = eng.support_run_ai(rec.rating_id)
    assert rec.ai_rating.value == "partially_supports"
    assert rec.ai_rating.provenance.model_id == "claude-opus-4-8"
    assert rec.adjudication.final_value is None        # AI is never final
    assert rec.blinding.independent is True


# ---- compare ---------------------------------------------------------------
def test_concordant_locks_in_human_value(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, pin_model=True)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="directly_supports"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_run_ai(rec.rating_id)
    rec = eng.support_compare(rec.rating_id)
    assert rec.comparison.status == "concordant"
    assert rec.adjudication.event == "accepted"
    assert rec.adjudication.final_value == "directly_supports"   # human-sourced


def test_discordant_needs_adjudication_no_auto_final(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, pin_model=True)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="does_not_support"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_run_ai(rec.rating_id)
    rec = eng.support_compare(rec.rating_id)
    assert rec.comparison.status == "discordant"
    assert rec.adjudication.final_value is None        # never auto-resolved


def test_ai_abstain_and_human_only(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, pin_model=True)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(abstained=True))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "indirectly_supports")
    # human-only (no AI yet)
    assert eng.support_compare(rec.rating_id).comparison.status == "human_only"
    eng.support_run_ai(rec.rating_id)
    assert eng.support_compare(rec.rating_id).comparison.status == "ai_abstained"


# ---- adjudicate ------------------------------------------------------------
def test_adjudication_is_the_only_path_to_final_on_discordance(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, pin_model=True)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="does_not_support"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_run_ai(rec.rating_id)
    eng.support_compare(rec.rating_id)
    rec = eng.support_adjudicate(rec.rating_id, "partially_supports",
                                 rationale="on review, support is partial", decider="human")
    assert rec.adjudication.event == "adjudicated"
    assert rec.adjudication.final_value == "partially_supports"


def test_human_may_adjudicate_to_the_ai_value(tmp_path):
    # allowed ONLY via explicit adjudication (never silently)
    store, claim_id, cand_id = _setup(tmp_path, pin_model=True)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="does_not_support"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_run_ai(rec.rating_id)
    eng.support_compare(rec.rating_id)
    rec = eng.support_adjudicate(rec.rating_id, "does_not_support",
                                 rationale="AI was right after re-reading", decider="human")
    assert rec.adjudication.final_value == "does_not_support"


def test_adjudication_requires_rationale(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, pin_model=True)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    with pytest.raises(ClaimSupportError):
        eng.support_adjudicate(rec.rating_id, "unclear", rationale="", decider="human")


# ---- audit + isolation -----------------------------------------------------
def test_support_ratings_are_audited_and_chain_verifies(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, pin_model=True)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="directly_supports"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_run_ai(rec.rating_id)
    eng.support_compare(rec.rating_id)
    assert "claim_support.save" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


def test_support_rating_does_not_mutate_evidence_map(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    before = store.load_evidence_map().model_dump()
    ClaimSupportEngine(store).support_start(claim_id, cand_id)
    assert store.load_evidence_map().model_dump() == before
