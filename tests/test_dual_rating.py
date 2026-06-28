"""Dual-rating engine: blinded human->AI->adjudication with the hardening invariants."""

import pytest

from citevahti.rating import FakeAiRater, RatingEngine
from citevahti.rating.blinding import blinded_ai_value
from citevahti.schemas.common import ItemRef
from citevahti.schemas.frame import Frame, Level, Outcome, Scheme, Study
from citevahti.schemas.rating import Subject
from citevahti.state import CiteVahtiStore
from citevahti.validators.errors import (
    FrameError,
    ModelNotPinnedError,
    RatingValidityError,
    TaskNotAllowedError,
)

GRADE = [Level(value="High", ordinal=4), Level(value="Moderate", ordinal=3),
         Level(value="Low", ordinal=2), Level(value="Very Low", ordinal=1)]
ROB = [Level(value="Low", ordinal=3), Level(value="Some concerns", ordinal=2),
       Level(value="High", ordinal=1)]


def make_frame():
    return Frame(frame_id="F", frame_version="1.0.0", created_at="2026-06-02T00:00:00+00:00",
                 outcomes=[Outcome(outcome_id="o1", label="Mortality")],
                 studies=[Study(study_id="s1", item=ItemRef(zotero_key="K1", citekey="smith2020"))],
                 schemes=[Scheme(scheme_id="grade", kind="GRADE", unit="outcome", levels=GRADE),
                          Scheme(scheme_id="rob2", kind="RoB2", unit="study", levels=ROB),
                          Scheme(scheme_id="rob2so", kind="RoB2", unit="study_x_outcome", levels=ROB)])


def engine(tmp_path, rater=None, pin=True):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_frame(make_frame())
    if pin:
        cfg = store.load_config()
        cfg.ai_provenance.model_id = "claude-opus-4-8"
        cfg.ai_provenance.model_snapshot = "2026-05-01"
        store.save_config(cfg)
    return RatingEngine(store, ai_rater=rater), store


def started(eng, scheme="grade", subject=None):
    return eng.rating_start("F", scheme, subject or Subject(outcome_id="o1"))


# ---- start + subject validation -------------------------------------------
def test_rating_start_creates_record(tmp_path):
    eng, store = engine(tmp_path)
    rec = started(eng)
    assert rec.frame_id == "F" and rec.scheme_id == "grade"
    assert rec.subject.outcome_id == "o1" and rec.frame_version == "1.0.0"
    assert store.load_rating(rec.rating_id).rating_id == rec.rating_id


def test_subject_validation_grade(tmp_path):
    eng, _ = engine(tmp_path)
    with pytest.raises(FrameError):
        eng.rating_start("F", "grade", Subject(study_id="s1"))   # GRADE needs outcome


def test_subject_validation_rob_study(tmp_path):
    eng, _ = engine(tmp_path)
    eng.rating_start("F", "rob2", Subject(study_id="s1"))
    with pytest.raises(FrameError):
        eng.rating_start("F", "rob2", Subject(outcome_id="o1"))


def test_subject_validation_rob_study_x_outcome(tmp_path):
    eng, _ = engine(tmp_path)
    eng.rating_start("F", "rob2so", Subject(study_id="s1", outcome_id="o1"))
    with pytest.raises(FrameError):
        eng.rating_start("F", "rob2so", Subject(study_id="s1"))   # needs both


# ---- human commit ----------------------------------------------------------
def test_human_commit_locks(tmp_path):
    eng, _ = engine(tmp_path)
    rec = eng.rating_commit_human(started(eng).rating_id, "Moderate")
    assert rec.human_rating.value == "Moderate" and rec.human_rating.locked is True


def test_second_human_commit_cannot_overwrite(tmp_path):
    eng, _ = engine(tmp_path)
    rid = started(eng).rating_id
    eng.rating_commit_human(rid, "Moderate")
    with pytest.raises(RatingValidityError):
        eng.rating_commit_human(rid, "Low")


# ---- AI run ----------------------------------------------------------------
def test_ai_run_refuses_unallowed_task(tmp_path):
    eng, _ = engine(tmp_path, rater=FakeAiRater("Moderate"))
    with pytest.raises(TaskNotAllowedError):
        eng.rating_run_ai(started(eng).rating_id, "frobnicate")


def test_ai_run_refuses_claim_check(tmp_path):
    eng, _ = engine(tmp_path, rater=FakeAiRater("Moderate"))
    with pytest.raises(TaskNotAllowedError):
        eng.rating_run_ai(started(eng).rating_id, "claim_check")   # assist, not rating


def test_ai_run_refuses_without_model_pin(tmp_path):
    eng, _ = engine(tmp_path, rater=FakeAiRater("Moderate"), pin=False)
    with pytest.raises(ModelNotPinnedError):
        eng.rating_run_ai(started(eng).rating_id, "assess")


def test_ai_value_stored_with_full_provenance(tmp_path):
    eng, _ = engine(tmp_path, rater=FakeAiRater("Moderate", confidence=0.8))
    rec = eng.rating_run_ai(started(eng).rating_id, "assess")
    ai = rec.ai_rating
    assert ai.value == "Moderate" and ai.abstained is False
    p = ai.provenance
    assert p.model_id == "claude-opus-4-8" and p.model_snapshot == "2026-05-01"
    assert p.prompt_hash and p.config_hash and p.rated_at and p.prompt_template_version


def test_ai_abstention_stored(tmp_path):
    eng, _ = engine(tmp_path, rater=FakeAiRater(abstained=True))
    rec = eng.rating_run_ai(started(eng).rating_id, "assess")
    assert rec.ai_rating.abstained is True and rec.ai_rating.value is None


# ---- compare ---------------------------------------------------------------
def _human_ai(tmp_path, human, ai_value=None, abstain=False):
    eng, store = engine(tmp_path, rater=FakeAiRater(ai_value, abstained=abstain))
    rid = started(eng).rating_id
    eng.rating_commit_human(rid, human)
    if ai_value is not None or abstain:
        eng.rating_run_ai(rid, "assess")
    return eng, store, rid


def test_concordant_is_accepted(tmp_path):
    eng, _, rid = _human_ai(tmp_path, "Moderate", "Moderate")
    cmp = eng.rating_compare(rid)
    assert cmp.status == "concordant" and cmp.outcome == "accepted"
    assert cmp.final_value == "Moderate"           # human-sourced


def test_discordant_needs_adjudication(tmp_path):
    eng, _, rid = _human_ai(tmp_path, "Low", "High")
    cmp = eng.rating_compare(rid)
    assert cmp.status == "discordant" and cmp.outcome == "needs_adjudication"
    assert cmp.final_value is None                 # not set without adjudication


def test_ai_abstained_outcome(tmp_path):
    eng, _, rid = _human_ai(tmp_path, "Moderate", abstain=True)
    cmp = eng.rating_compare(rid)
    assert cmp.status == "ai_abstained" and cmp.agreement_countable is False


def test_human_only_outcome(tmp_path):
    eng, _ = engine(tmp_path)
    rid = started(eng).rating_id
    eng.rating_commit_human(rid, "Moderate")
    cmp = eng.rating_compare(rid)               # no AI run
    assert cmp.status == "human_only" and cmp.agreement_countable is False


# ---- adjudication ----------------------------------------------------------
def test_discordant_cannot_set_final_without_adjudication(tmp_path):
    eng, store, rid = _human_ai(tmp_path, "Low", "High")
    eng.rating_compare(rid)
    rec = store.load_rating(rid)
    assert rec.comparison.status == "discordant"
    assert rec.adjudication.final_value is None and rec.adjudication.event is None


def test_adjudication_sets_human_panel_final(tmp_path):
    eng, _, rid = _human_ai(tmp_path, "Low", "High")
    eng.rating_compare(rid)
    rec = eng.rating_adjudicate(rid, "Low", rationale="panel reviewed domains", decider="panel")
    assert rec.adjudication.final_value == "Low"
    assert rec.adjudication.event == "adjudicated" and rec.adjudication.decided_by == "panel"


def test_ai_value_never_auto_copied_to_final(tmp_path):
    eng, store, rid = _human_ai(tmp_path, "Low", "High")
    eng.rating_compare(rid)
    rec = store.load_rating(rid)
    assert rec.adjudication.final_value != rec.ai_rating.value   # AI High never became final


def test_audit_event_on_each_mutation(tmp_path):
    eng, store, rid = _human_ai(tmp_path, "Moderate", "Moderate")
    eng.rating_compare(rid)
    eng.rating_adjudicate(rid, "Moderate", rationale="confirm", decider="human")
    saves = [e for e in store.audit.entries() if e.event == "rating.save"]
    assert len(saves) >= 4                        # start, commit, run_ai, compare, adjudicate
    assert store.audit.verify() is True


# ---- flag/score behaviour (added coverage) ---------------------------------
def test_ai_value_sealed_until_human_rates(tmp_path):
    """Invariant: an AI rating recorded BEFORE the human rates stays blinded; it is
    revealed only once a human value exists (the blinding window, through the engine)."""
    eng, store = engine(tmp_path, rater=FakeAiRater("Moderate"))
    rid = started(eng).rating_id
    eng.rating_run_ai(rid, "assess")                 # AI first — human has NOT rated yet
    rec = store.load_rating(rid)
    assert rec.human_rating is None and rec.ai_rating.value == "Moderate"
    # Sealed while no human value exists.
    assert blinded_ai_value(None, rec.ai_rating.value, hidden="SEALED") == "SEALED"
    # Once the human commits, the same rule reveals it.
    eng.rating_commit_human(rid, "Low")
    rec = store.load_rating(rid)
    assert blinded_ai_value(rec.human_rating.value, rec.ai_rating.value, hidden="SEALED") == "Moderate"


def test_compare_sets_computed_at(tmp_path):
    """compare() stamps comparison.computed_at; it is unset until compare runs."""
    eng, store, rid = _human_ai(tmp_path, "Moderate", "Moderate")
    assert store.load_rating(rid).comparison.computed_at is None
    eng.rating_compare(rid)
    stamped = store.load_rating(rid).comparison.computed_at
    assert stamped is not None and "T" in stamped     # ISO-8601


def test_compare_reports_agreement_countable_per_outcome(tmp_path):
    """agreement_countable is True only for concordant/discordant — the comparable pairs."""
    eng_c, _, rid_c = _human_ai(tmp_path / "concordant", "Moderate", "Moderate")
    eng_d, _, rid_d = _human_ai(tmp_path / "discordant", "Low", "High")
    eng_a, _, rid_a = _human_ai(tmp_path / "abstained", "Moderate", abstain=True)
    eng_h, _ = engine(tmp_path / "human_only")
    rid_h = started(eng_h).rating_id
    eng_h.rating_commit_human(rid_h, "Moderate")
    assert eng_c.rating_compare(rid_c).agreement_countable is True
    assert eng_d.rating_compare(rid_d).agreement_countable is True
    assert eng_a.rating_compare(rid_a).agreement_countable is False
    assert eng_h.rating_compare(rid_h).agreement_countable is False


def test_adjudication_requires_rationale(tmp_path):
    """A final value can never be set by adjudication without a recorded rationale."""
    eng, _, rid = _human_ai(tmp_path, "Low", "High")
    eng.rating_compare(rid)
    with pytest.raises(RatingValidityError):
        eng.rating_adjudicate(rid, "Low", rationale="", decider="human")


def test_adjudication_rejects_non_human_decider(tmp_path):
    """Only a human or a panel may adjudicate — never the AI (or any other actor)."""
    eng, _, rid = _human_ai(tmp_path, "Low", "High")
    eng.rating_compare(rid)
    with pytest.raises(RatingValidityError):
        eng.rating_adjudicate(rid, "Low", rationale="ai chose", decider="ai")


def test_concordant_accept_is_overridable_only_by_explicit_adjudication(tmp_path):
    """A concordant pair auto-accepts the HUMAN value; a human may still revise it, but
    only via an explicit 'adjudicated' event carrying a rationale — never silently."""
    eng, store, rid = _human_ai(tmp_path, "Moderate", "Moderate")
    cmp = eng.rating_compare(rid)
    assert cmp.final_value == "Moderate"
    assert store.load_rating(rid).adjudication.event == "accepted"
    rec = eng.rating_adjudicate(rid, "Low", rationale="human revised after re-reading",
                                decider="human")
    assert rec.adjudication.final_value == "Low"
    assert rec.adjudication.event == "adjudicated" and rec.adjudication.rationale
