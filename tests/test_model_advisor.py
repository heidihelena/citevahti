"""Model second-opinion advisor (ADR-0009 §3b) — the read-only surface that answers
"which AI model should I trust as a second opinion?" from THIS project's own record
of validated divergences.

The rules under test, all cheese-hole (complementary value, never agreement):
- a model is ranked only once it clears the evidence floor of resolved divergences;
- ranking is by catch-rate (catches / resolved), not by how often it agreed;
- a named model that rates low gets a better-evidenced alternative suggested;
- the advisor writes NOTHING — no exports/, no audit entry (read-only invariant).

Offline: imports repo files only.
"""

from __future__ import annotations

from citevahti.export import AgreementReportService
from citevahti.export.agreement import _MIN_RESOLVED
from citevahti.schemas.common import ItemRef
from citevahti.schemas.frame import Frame, Level, Outcome, Scheme, Study
from citevahti.schemas.rating import (
    Adjudication,
    AIProvenance,
    AIRating,
    Comparison,
    HumanRating,
    RatingRecord,
    Subject,
)
from citevahti.state import CiteVahtiStore

GRADE = [Level(value="High", ordinal=4), Level(value="Moderate", ordinal=3),
         Level(value="Low", ordinal=2), Level(value="Very Low", ordinal=1)]


def _store(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    frame = Frame(
        frame_id="F", frame_version="1.0.0", created_at="2026-06-02T00:00:00+00:00",
        outcomes=[Outcome(outcome_id=f"o{i}", label=f"O{i}") for i in range(1, 40)],
        studies=[Study(study_id=f"s{i}", item=ItemRef(zotero_key=f"K{i}", citekey=f"c{i}"))
                 for i in range(1, 40)],
        schemes=[Scheme(scheme_id="grade", kind="GRADE", unit="outcome", levels=GRADE)])
    store.save_frame(frame)
    return store, frame


def _prov(model_id, snapshot="s1"):
    return AIProvenance(provider="anthropic", model_id=model_id, model_snapshot=snapshot,
                        prompt_template_version="v1", prompt_hash="ph", config_hash="ch",
                        rated_at="2026-06-02T00:00:00+00:00")


def _add(store, frame, rid, outcome, human, ai, status, model_id, *,
         adjudicated=False, final=None):
    adj = (Adjudication(final_value=final, event="adjudicated", decided_by="panel", rationale="r")
           if adjudicated else Adjudication())
    store.save_rating(RatingRecord(
        rating_id=rid, frame_id="F", frame_version="1.0.0", scheme_id="grade",
        subject=Subject(outcome_id=outcome),
        human_rating=HumanRating(value=human, committed_at="2026-06-02T00:00:00+00:00",
                                 committed_by="rater"),
        ai_rating=AIRating(value=ai, abstained=False, provenance=_prov(model_id), task_type="assess"),
        comparison=Comparison(status=status), adjudication=adj), frame=frame)


def _catch(store, frame, rid, outcome, model_id):
    # discordant, adjudicated toward the AI -> a validated catch
    _add(store, frame, rid, outcome, "Low", "High", "discordant", model_id,
         adjudicated=True, final="High")


def _overruled(store, frame, rid, outcome, model_id):
    # discordant, adjudicated toward the human -> overruled
    _add(store, frame, rid, outcome, "Low", "High", "discordant", model_id,
         adjudicated=True, final="Low")


def test_below_the_floor_no_model_is_ranked(tmp_path):
    store, frame = _store(tmp_path)
    _catch(store, frame, "r1", "o1", "model-a")   # 1 resolved divergence only
    advice = AgreementReportService(store).advise_models()
    assert advice.recommended is None
    assert [m.model_id for m in advice.ranked] == []
    assert "model-a (s1)" in advice.under_evidenced


def test_ranks_by_catch_rate_and_recommends_the_best(tmp_path):
    store, frame = _store(tmp_path)
    # model-a: 5 catches, 0 overruled -> catch_rate 1.0 (clears the floor of 5 resolved)
    for i in range(_MIN_RESOLVED):
        _catch(store, frame, f"a{i}", f"o{i + 1}", "model-a")
    # model-b: 2 catches, 4 overruled -> catch_rate 0.333 (6 resolved, clears floor)
    for i in range(2):
        _catch(store, frame, f"bc{i}", f"o{i + 10}", "model-b")
    for i in range(4):
        _overruled(store, frame, f"bo{i}", f"o{i + 20}", "model-b")

    advice = AgreementReportService(store).advise_models()
    assert [m.model_id for m in advice.ranked] == ["model-a", "model-b"]
    assert advice.recommended == "model-a (s1)"


def test_low_rated_named_model_gets_an_alternative_suggested(tmp_path):
    store, frame = _store(tmp_path)
    # strong alternative
    for i in range(_MIN_RESOLVED):
        _catch(store, frame, f"a{i}", f"o{i + 1}", "model-a")
    # the model the user is asking about rates low: 1 catch, 4 overruled -> 0.2
    _catch(store, frame, "b0", "o10", "model-b")
    for i in range(4):
        _overruled(store, frame, f"bo{i}", f"o{i + 20}", "model-b")

    advice = AgreementReportService(store).advise_models("model-b")
    assert advice.asked_about == "model-b"
    assert advice.asked_catch_rate == 0.2
    assert advice.suggestion is not None
    assert "model-a (s1)" in advice.suggestion


def test_high_rated_named_model_gets_no_switch_suggestion(tmp_path):
    store, frame = _store(tmp_path)
    for i in range(_MIN_RESOLVED):
        _catch(store, frame, f"a{i}", f"o{i + 1}", "model-a")
    advice = AgreementReportService(store).advise_models("model-a")
    assert advice.suggestion is None
    assert advice.asked_catch_rate == 1.0


def test_agreement_alone_earns_nothing(tmp_path):
    store, frame = _store(tmp_path)
    # a model that only ever agrees with the human: many concordant, zero divergence
    for i in range(10):
        _add(store, frame, f"c{i}", f"o{i + 1}", "High", "High", "concordant", "yes-model")
    advice = AgreementReportService(store).advise_models("yes-model")
    assert advice.recommended is None          # no catches -> ranks nowhere
    assert advice.asked_catch_rate is None     # no resolved divergences to rate


def test_advisor_writes_nothing(tmp_path):
    store, frame = _store(tmp_path)
    _catch(store, frame, "r1", "o1", "model-a")
    before = sorted(p.name for p in tmp_path.rglob("*"))
    AgreementReportService(store).advise_models("model-a")
    after = sorted(p.name for p in tmp_path.rglob("*"))
    assert before == after
