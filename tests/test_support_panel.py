"""Organized-panel "X of N support" aggregate (ADR-0008, the review/guideline tiers).

Multiple named human reviewers rate the SAME (claim, candidate); the aggregate counts how many
of N support the claim, the distribution, raw agreement, and the confidence tier. Built on the
existing spine (support_start + support_commit_human with distinct committed_by) — no new core.
The AI second opinion is never a panel member.
"""

from citevahti.claims import CandidateService, ClaimService, ClaimSupportEngine, FakeClaimSupportRater
from citevahti.claims.panel import claim_panel_summary, panel_summary, tier_of
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
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


def _vote(store, claim_id, cand_id, votes: dict, ai=None):
    """Record one human rating per rater (distinct committed_by) for the pair."""
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value=ai, abstained=ai is None)
                             if ai is not None else None)
    for rater, value in votes.items():
        rec = eng.support_start(claim_id, cand_id, rating_set_id="panel-1")
        eng.support_commit_human(rec.rating_id, value, committed_by=rater)
        if ai is not None:
            eng.support_run_ai(rec.rating_id)   # AI rides along — must NOT count in the panel


def test_tier_boundaries():
    assert tier_of(0) == "none"
    assert tier_of(1) == "individual"
    assert tier_of(2) == "review" and tier_of(7) == "review"
    assert tier_of(8) == "guideline" and tier_of(12) == "guideline"


def test_panel_counts_human_raters_only(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    # 6 reviewers: 4 support (mix of strengths), 2 do not → "4 of 6 support", review-level
    _vote(store, claim_id, cand_id, {
        "r1": "directly_supports", "r2": "partially_supports", "r3": "indirectly_supports",
        "r4": "directly_supports", "r5": "does_not_support", "r6": "contradicts"},
        ai="directly_supports")
    s = panel_summary(store, claim_id, cand_id)
    assert s["n_raters"] == 6                       # AI did not inflate N
    assert s["support_count"] == 4
    assert s["headline"] == "4 of 6 support"
    assert s["tier"] == "review"
    assert s["distribution"]["directly_supports"] == 2
    assert s["raw_agreement"] == round(2 / 6, 2)    # modal value count / N


def test_overstated_is_not_counted_as_support(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    _vote(store, claim_id, cand_id, {"a": "directly_supports", "b": "overstated", "c": "unclear"})
    s = panel_summary(store, claim_id, cand_id)
    assert s["n_raters"] == 3 and s["support_count"] == 1   # overstated/unclear are not support
    assert s["headline"] == "1 of 3 support"


def test_guideline_tier_at_eight_raters(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    votes = {f"rev{i}": ("directly_supports" if i <= 7 else "does_not_support") for i in range(1, 9)}
    _vote(store, claim_id, cand_id, votes)
    s = panel_summary(store, claim_id, cand_id)
    assert s["n_raters"] == 8 and s["support_count"] == 7
    assert s["tier"] == "guideline" and s["headline"] == "7 of 8 support"


def test_one_rater_is_individual_and_resave_does_not_double_count(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    # the same rater rating twice must still be ONE rater (grouped by committed_by)
    _vote(store, claim_id, cand_id, {"solo": "directly_supports"})
    _vote(store, claim_id, cand_id, {"solo": "partially_supports"})
    s = panel_summary(store, claim_id, cand_id)
    assert s["n_raters"] == 1 and s["tier"] == "individual"


def test_claim_rollup_uses_widest_panel(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    _vote(store, claim_id, cand_id, {"r1": "directly_supports", "r2": "partially_supports"})
    roll = claim_panel_summary(store, claim_id)
    assert roll["tier"] == "review"
    assert roll["candidates"] and roll["candidates"][0]["n_raters"] == 2


def test_tool_and_agent_free_read(tmp_path):
    from citevahti import tools
    store, claim_id, cand_id = _setup(tmp_path)
    _vote(store, claim_id, cand_id, {"r1": "directly_supports", "r2": "does_not_support"})
    out = tools.support_panel(claim_id, cand_id, root=str(tmp_path))
    assert out["headline"] == "1 of 2 support" and out["tier"] == "review"
    whole = tools.support_panel(claim_id, root=str(tmp_path))
    assert whole["tier"] == "review" and len(whole["candidates"]) == 1
