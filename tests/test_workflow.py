"""The workflow resolver: the single source of truth for phase + next action.

Read-only and pure where it can be. These guard the de-duplicated phase machine
(every surface renders this instead of re-deriving rate→decide→write), the blinding
rule (reveal only after the human rates), and the project-level next action.
"""

from citevahti import workflow


# ---- per-candidate phase -----------------------------------------------------
def test_candidate_phase_walks_rate_decide_write_done():
    assert workflow.candidate_phase(has_human_rating=False, has_decision=False, written=False) == "rate"
    assert workflow.candidate_phase(has_human_rating=True, has_decision=False, written=False) == "decide"
    assert workflow.candidate_phase(has_human_rating=True, has_decision=True, written=False) == "write"
    assert workflow.candidate_phase(has_human_rating=True, has_decision=True, written=True) == "done"


def test_written_is_done_even_if_other_facts_lag():
    # a committed write is terminal regardless of the intermediate flags
    assert workflow.candidate_phase(has_human_rating=False, has_decision=False, written=True) == "done"


def test_reveal_only_after_the_human_rates():
    assert workflow.reveal_ready(has_human_rating=False, has_ai_rating=True) is False  # blinded
    assert workflow.reveal_ready(has_human_rating=True, has_ai_rating=False) is False  # nothing to show
    assert workflow.reveal_ready(has_human_rating=True, has_ai_rating=True) is True


def test_candidate_step_offers_verdicts_only_when_deciding():
    deciding = workflow.candidate_step(has_human_rating=True, has_ai_rating=True,
                                       has_decision=False, written=False)
    assert deciding["phase"] == "decide"
    assert deciding["reveal_ready"] is True
    assert [v["decision"] for v in deciding["allowed_verdicts"]] == \
        ["accept", "accepted_with_caution", "needs_second_review", "reject"]

    rating = workflow.candidate_step(has_human_rating=False, has_ai_rating=False,
                                     has_decision=False, written=False)
    assert rating["phase"] == "rate"
    assert rating["allowed_verdicts"] == []          # no verdict keys before a rating exists


# ---- vocabulary (one definition; surfaces render it) -------------------------
def test_vocabulary_is_the_single_source_of_verdicts_and_states():
    vocab = workflow.vocabulary()
    assert {v["decision"] for v in vocab["verdicts"]} == \
        {"accept", "accepted_with_caution", "needs_second_review", "reject"}
    # the verdict codes line up with the report's accepted/caution/review/reject codes
    by_decision = {v["decision"]: v["code"] for v in vocab["verdicts"]}
    assert by_decision["accept"] == "oo" and by_decision["reject"] == "d"
    assert {s["state"] for s in vocab["states"]} >= {"accepted", "needs_support", "review_needed"}
    assert "rate" in vocab["phases"] and "done" in vocab["phases"]


# ---- project-level next action -----------------------------------------------
def test_project_status_on_uninitialized_project_points_to_init(tmp_path):
    st = workflow.project_status(str(tmp_path))
    assert st["ready"] is False
    assert st["blockers"] == ["not_initialized"]
    assert st["next"]["kind"] == "init"


def test_project_status_empty_ledger_asks_for_a_manuscript(tmp_path):
    from citevahti.state import CiteVahtiStore
    CiteVahtiStore(str(tmp_path)).init()
    st = workflow.project_status(str(tmp_path))   # no live Zotero in tests -> soft blocker
    assert st["claims_total"] == 0
    assert st["next"]["kind"] == "add_claims"
    assert "zotero_not_write_ready" in st["blockers"]


def test_next_action_prioritises_pending_ratings_then_report():
    # with pending claims, the next action is to rate; otherwise export the report
    rate = workflow._next_action("/nonexistent", total=3,
                                 counts={"needs_support": 2, "review_needed": 1})
    assert rate["kind"] == "rate"
    done = workflow._next_action("/nonexistent", total=3,
                                 counts={"needs_support": 0, "review_needed": 0})
    assert done["kind"] == "report"
