"""Regression: starting a claim-support rating twice must not fork the pair in two.

Found loading a real corpus (30 claims / 61 candidate pairs) through the CLI: an agent
loader that called `claim-support-start` for each pair on two passes left **118 support
records for 61 pairs**. Every duplicate is a second, unrated record of a judgement that was
only ever made once — whichever the rater commits, the other lingers open, and any later
comparison, panel count, or agreement report has to guess which one represents the pair.

So opening a rating is idempotent: a pair with an open (human-unrated) rating gets that
same rating back, and nothing is written. What must NOT break is the panel — several named
reviewers rating the SAME pair, each needing a record of their own (ADR-0008). A rating
holding a human value is never handed out again, which keeps sequential panel raters
working; `force_new` covers reviewers who need open slots at the same time.

Offline: fake provider + fake rater, no network.
"""

from __future__ import annotations

import json

from citevahti.claims import CandidateService, ClaimService, ClaimSupportEngine, FakeClaimSupportRater
from citevahti.claims.panel import panel_summary
from citevahti.claims.support import open_support_rating
from citevahti.cli import main
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore


class _Provider:
    name = "pubmed"

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(
            status="ok", count=1, email_present=True, rate_tier="3rps",
            hits=[ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873", title="NLST")])


def _seed(tmp_path):
    store = CiteVahtiStore(str(tmp_path))
    store.init()
    cfg = store.load_config()
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    cfg.ai_provenance.prompt_template_version = "v1"
    store.save_config(cfg)
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(),
                          library_index=StaticLibraryIndex()).literature_search(
                              "ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return store, claim.claim_id, cand_id


def _ratings_for(store, claim_id, cand_id):
    return [r for r in (store.load_support_rating(i) for i in store.list_support_ratings())
            if r.claim_id == claim_id and r.candidate_id == cand_id]


# ---- the bug -------------------------------------------------------------------------

def test_starting_twice_yields_one_rating(tmp_path):
    """THE regression: two starts for one pair leave one record, not two."""
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store)

    first = eng.support_start(claim_id, cand_id)
    second = eng.support_start(claim_id, cand_id)

    assert second.rating_id == first.rating_id
    assert len(_ratings_for(store, claim_id, cand_id)) == 1


def test_a_repeated_start_is_a_read_and_writes_nothing(tmp_path):
    """Starting is a request for a slot, not an event: the repeat appends no audit entry
    and no access-log line, so a retried loader leaves no trace of a start that didn't
    happen."""
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store)
    first = eng.support_start(claim_id, cand_id)
    audit_before = len(store.audit.entries())
    log_before = len(first.blinding.access_log)

    again = eng.support_start(claim_id, cand_id)

    assert len(store.audit.entries()) == audit_before
    assert len(again.blinding.access_log) == log_before


def test_a_loader_that_retries_every_pair_does_not_double_the_ledger(tmp_path):
    """The measured failure, in miniature: two full passes over the corpus must leave one
    record per pair — not 2N."""
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store)
    for _ in range(2):
        eng.support_start(claim_id, cand_id)
    assert len(store.list_support_ratings()) == 1


# ---- what must keep working: the panel ------------------------------------------------

def test_a_rated_slot_is_never_handed_out_again(tmp_path):
    """Reviewer 2 must not be given reviewer 1's committed rating — that would either
    overwrite a locked human value or silently drop the second judgement."""
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store)
    r1 = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(r1.rating_id, "directly_supports", committed_by="reviewer-1")

    r2 = eng.support_start(claim_id, cand_id)

    assert r2.rating_id != r1.rating_id
    assert r2.human_rating is None


def test_sequential_panel_still_counts_every_reviewer(tmp_path):
    """The ADR-0008 panel workflow end-to-end: start → commit per reviewer still yields
    N independent raters, so idempotence cannot deflate an "X of N support" headline."""
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store)
    votes = {"reviewer-1": "directly_supports", "reviewer-2": "partially_supports",
             "reviewer-3": "does_not_support"}
    for rater, value in votes.items():
        rec = eng.support_start(claim_id, cand_id, rating_set_id="panel-1")
        eng.support_commit_human(rec.rating_id, value, committed_by=rater)

    summary = panel_summary(store, claim_id, cand_id)
    assert summary["n_raters"] == 3
    assert summary["headline"] == "2 of 3 support"


def test_force_new_opens_an_independent_slot_for_a_concurrent_reviewer(tmp_path):
    """Reviewers who hold open slots at the same time ask for one explicitly."""
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store)
    a = eng.support_start(claim_id, cand_id)
    b = eng.support_start(claim_id, cand_id, force_new=True)

    assert b.rating_id != a.rating_id
    eng.support_commit_human(a.rating_id, "directly_supports", committed_by="reviewer-1")
    eng.support_commit_human(b.rating_id, "does_not_support", committed_by="reviewer-2")
    assert panel_summary(store, claim_id, cand_id)["n_raters"] == 2


def test_separate_rating_sets_never_share_a_slot(tmp_path):
    """Two panels rating the same pair are two exercises; neither inherits the other's
    open slot."""
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store)
    a = eng.support_start(claim_id, cand_id, rating_set_id="panel-1")
    b = eng.support_start(claim_id, cand_id, rating_set_id="panel-2")
    assert a.rating_id != b.rating_id
    assert eng.support_start(claim_id, cand_id, rating_set_id="panel-1").rating_id == a.rating_id


# ---- blinding -------------------------------------------------------------------------

def test_an_ai_rating_does_not_close_a_slot(tmp_path):
    """The AI is an advisory second rater, never the pair's rater: a slot it has rated is
    still waiting for its human, so a restart returns it rather than minting a rival."""
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="directly_supports"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_run_ai(rec.rating_id)

    again = eng.support_start(claim_id, cand_id)
    assert again.rating_id == rec.rating_id
    assert open_support_rating(store, claim_id, cand_id).rating_id == rec.rating_id


def test_restart_json_never_leaks_the_blinded_ai_value(tmp_path, capsys):
    """`claim-support-start --json` hands back a rating that may ALREADY hold an AI value.
    It must emit identity only — dumping the record would reveal the AI's judgement before
    the human rates, which is the one thing blinding exists to prevent."""
    store, claim_id, cand_id = _seed(tmp_path)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="contradicts"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_run_ai(rec.rating_id)
    capsys.readouterr()

    main(["--root", str(tmp_path), "claim-support-start", "--claim-id", claim_id,
          "--candidate-id", cand_id, "--json"])
    out = capsys.readouterr().out
    res = json.loads(out)

    assert res["rating_id"] == rec.rating_id          # same slot, not a second one
    assert res["ai_recorded"] is True                 # existence is disclosed...
    assert "contradicts" not in out                   # ...the judgement is not
    assert res["blinded"] is True
