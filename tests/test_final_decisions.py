"""Final decisions (ADR-0001 step 4): the human-owned terminal judgment.

The mission invariant: you cannot ACCEPT a citation whose final support judgment
does not support the claim. You also cannot finalize accept/reject on an
unresolved discordance — adjudicate first or record needs_second_review.
"""

import pytest

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
    FakeClaimSupportRater,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore
from citevahti.state.store import StateError
from citevahti.validators.claim_support import ClaimSupportError
from citevahti.validators.decision import DecisionError


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


def _rate(store, claim_id, cand_id, human, ai=None, adjudicate=None):
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(
        value=ai, abstained=(ai is None)) if ai is not None else None)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, human)
    if ai is not None:
        eng.support_run_ai(rec.rating_id)
    eng.support_compare(rec.rating_id)
    if adjudicate is not None:
        eng.support_adjudicate(rec.rating_id, adjudicate, rationale="reviewed", decider="human")
    return rec.rating_id


# ---- happy path: concordant support -> accept ------------------------------
def test_accept_on_concordant_supporting_rating(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    dec = DecisionService(store).decide(
        claim_id, cand_id, "accept", "primary endpoint supports the claim", rating_id=rid)
    assert dec.final_decision == "accept"
    assert dec.final_support_status == "directly_supports"
    assert dec.agreement_status == "concordant"


# ---- mission invariant: cannot accept a non-supporting paper ---------------
def test_cannot_accept_a_non_supporting_paper(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    # human + AI agree it does NOT support
    rid = _rate(store, claim_id, cand_id, "does_not_support", ai="does_not_support")
    with pytest.raises(DecisionError):
        DecisionService(store).decide(
            claim_id, cand_id, "accept", "trying to accept anyway", rating_id=rid)
    # rejecting it is fine
    dec = DecisionService(store).decide(
        claim_id, cand_id, "reject", "does not support the claim", rating_id=rid)
    assert dec.final_decision == "reject" and dec.final_support_status == "does_not_support"


def test_cannot_accept_without_a_support_rating(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    with pytest.raises(DecisionError):
        DecisionService(store).decide(claim_id, cand_id, "accept", "no rating exists")


# ---- unresolved discordance must be needs_second_review --------------------
def test_unresolved_discordance_blocks_accept_and_reject(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="does_not_support")  # discordant
    svc = DecisionService(store)
    with pytest.raises(DecisionError):
        svc.decide(claim_id, cand_id, "accept", "x", rating_id=rid)
    with pytest.raises(DecisionError):
        svc.decide(claim_id, cand_id, "reject", "x", rating_id=rid)
    # needs_second_review is allowed
    dec = svc.decide(claim_id, cand_id, "needs_second_review", "raters disagree", rating_id=rid)
    assert dec.final_decision == "needs_second_review" and dec.final_support_status is None


def test_adjudicated_discordance_can_be_accepted(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="does_not_support",
                adjudicate="partially_supports")
    dec = DecisionService(store).decide(
        claim_id, cand_id, "accept", "partial support confirmed on review", rating_id=rid)
    assert dec.final_decision == "accept" and dec.final_support_status == "partially_supports"


def test_accepted_with_caution_requires_support(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "indirectly_supports", ai="indirectly_supports")
    dec = DecisionService(store).decide(
        claim_id, cand_id, "accepted_with_caution", "indirect but relevant", rating_id=rid)
    assert dec.final_decision == "accepted_with_caution"


# ---- basic guards ----------------------------------------------------------
def test_decision_requires_reason(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    with pytest.raises(DecisionError):
        DecisionService(store).decide(claim_id, cand_id, "needs_second_review", "")


def test_bad_decision_value_rejected(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    with pytest.raises(Exception):
        DecisionService(store).decide(claim_id, cand_id, "maybe", "reason")


def test_decide_on_missing_candidate_raises(tmp_path):
    store, claim_id, _cand_id = _setup(tmp_path)
    with pytest.raises(DecisionError):
        DecisionService(store).decide(claim_id, "cand-nope", "reject", "x")


def test_rating_for_other_pair_rejected(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    # a second claim with no candidates -> using the first rating is a mismatch
    other = ClaimService(store).add_claim("other claim", "background")
    with pytest.raises(StateError):  # no candidates linked to the other claim
        DecisionService(store).decide(other.claim_id, cand_id, "accept", "x", rating_id=rid)


# ---- audit + isolation -----------------------------------------------------
def test_decision_is_audited_and_chain_verifies(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    DecisionService(store).decide(claim_id, cand_id, "accept", "supports", rating_id=rid)
    assert "decision.final" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


def test_one_decision_per_pair_revision_overwrites(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    svc = DecisionService(store)
    svc.decide(claim_id, cand_id, "needs_second_review", "hold", rating_id=rid)
    svc.decide(claim_id, cand_id, "accept", "now accepting", rating_id=rid)
    assert len(svc.list_for_claim(claim_id)) == 1
    assert svc.get(cand_id).final_decision == "accept"


def test_decision_does_not_mutate_evidence_map(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    before = store.load_evidence_map().model_dump()
    DecisionService(store).decide(claim_id, cand_id, "accept", "ok", rating_id=rid)
    assert store.load_evidence_map().model_dump() == before


# ---- regression: the adjudication-precondition hole (external review, v0.14.0) -
def test_adjudication_refused_without_human_ai_discordance(tmp_path):
    """support_adjudicate must NOT fabricate a resolved final value: it requires a
    locked human rating, an AI second rating, and a COMPUTED discordance."""
    store, claim_id, cand_id = _setup(tmp_path)

    # (a) no human rating at all -> refuse, and fabricate nothing
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="contradicts"))
    bare = eng.support_start(claim_id, cand_id)
    with pytest.raises(ClaimSupportError):
        eng.support_adjudicate(bare.rating_id, "directly_supports", rationale="override")
    r = store.load_support_rating(bare.rating_id)
    assert r.adjudication.final_value is None and r.comparison.status is None

    # (b) human only (no AI) -> refuse
    ho = ClaimSupportEngine(store).support_start(claim_id, cand_id)
    eng_ho = ClaimSupportEngine(store)
    eng_ho.support_commit_human(ho.rating_id, "directly_supports")
    eng_ho.support_compare(ho.rating_id)            # status = human_only
    with pytest.raises(ClaimSupportError):
        eng_ho.support_adjudicate(ho.rating_id, "contradicts", rationale="override")

    # (c) concordant (human == AI) -> refuse (no disagreement to resolve)
    engc = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="directly_supports"))
    con = engc.support_start(claim_id, cand_id)
    engc.support_commit_human(con.rating_id, "directly_supports")
    engc.support_run_ai(con.rating_id)
    engc.support_compare(con.rating_id)             # concordant
    with pytest.raises(ClaimSupportError):
        engc.support_adjudicate(con.rating_id, "contradicts", rationale="override")

    # (d) a genuine discordance -> adjudication is allowed
    engd = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="contradicts"))
    dis = engd.support_start(claim_id, cand_id)
    engd.support_commit_human(dis.rating_id, "directly_supports")
    engd.support_run_ai(dis.rating_id)
    engd.support_compare(dis.rating_id)             # discordant
    out = engd.support_adjudicate(dis.rating_id, "directly_supports", rationale="reviewed")
    assert out.adjudication.final_value == "directly_supports"


def test_decision_cannot_accept_an_unrated_pair(tmp_path):
    """End-to-end: with no human rating there is no path to an accept decision."""
    store, claim_id, cand_id = _setup(tmp_path)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="contradicts"))
    rec = eng.support_start(claim_id, cand_id)
    with pytest.raises(ClaimSupportError):          # the old hole: fake-adjudicate then accept
        eng.support_adjudicate(rec.rating_id, "directly_supports", rationale="override")
    with pytest.raises(DecisionError):              # and the unresolved pair cannot be accepted
        DecisionService(store).decide(claim_id, cand_id, "accept", "reason", rating_id=rec.rating_id)


# ---- guarded remove may not orphan a recorded decision ----------------------
def test_unlink_refused_after_a_decision_is_recorded(tmp_path):
    """A candidate with a final decision (and so possibly a Zotero write) cannot
    be unlinked — that would orphan the decision and leave the claim showing a
    verdict for a paper no longer in its candidate set. Undo the decision first."""
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    DecisionService(store).decide(claim_id, cand_id, "accept",
                                  "primary endpoint supports the claim", rating_id=rid)
    with pytest.raises(StateError) as ei:
        store.unlink_candidate(claim_id, cand_id)
    assert getattr(ei.value, "code", None) == "candidate_decided"
    # refused atomically: the candidate is still linked
    assert any(c.candidate_id == cand_id for c in store.load_candidates(claim_id).candidates)


def test_unlink_allowed_before_a_decision(tmp_path):
    """Before any verdict, unlinking the wrong paper is fine (the common case)."""
    store, claim_id, cand_id = _setup(tmp_path)
    _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")  # rated, not decided
    out = store.unlink_candidate(claim_id, cand_id)
    assert all(c.candidate_id != cand_id for c in out.candidates)
