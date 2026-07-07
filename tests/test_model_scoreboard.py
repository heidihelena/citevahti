"""Per-model complementary-catch scoreboard (ADR-0009 §3b) — the local precursor to
the Atlas model scoreboard. A model earns a CATCH only for a *validated divergence*:
it disagreed with the human and the human's adjudicated final matched the AI. Mere
agreement scores nothing. Read-only over existing rating records — this test also
pins that the report writes nothing when persist=False.
"""

from __future__ import annotations

from citevahti.export import AgreementReportService
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
        outcomes=[Outcome(outcome_id=f"o{i}", label=f"O{i}") for i in range(1, 6)],
        studies=[Study(study_id=f"s{i}", item=ItemRef(zotero_key=f"K{i}", citekey=f"c{i}"))
                 for i in range(1, 6)],
        schemes=[Scheme(scheme_id="grade", kind="GRADE", unit="outcome", levels=GRADE)])
    store.save_frame(frame)
    return store, frame


def _prov():
    return AIProvenance(provider="anthropic", model_id="claude-opus-4-8",
                        model_snapshot="2026-05-01", prompt_template_version="v1",
                        prompt_hash="ph", config_hash="ch", rated_at="2026-06-02T00:00:00+00:00")


def _add(store, frame, rid, outcome, human, ai, status, *, adjudicated=False, final=None):
    adj = (Adjudication(final_value=final, event="adjudicated", decided_by="panel", rationale="r")
           if adjudicated else Adjudication())
    store.save_rating(RatingRecord(
        rating_id=rid, frame_id="F", frame_version="1.0.0", scheme_id="grade",
        subject=Subject(outcome_id=outcome),
        human_rating=HumanRating(value=human, committed_at="2026-06-02T00:00:00+00:00",
                                 committed_by="rater"),
        ai_rating=AIRating(value=ai, abstained=False, provenance=_prov(), task_type="assess"),
        comparison=Comparison(status=status), adjudication=adj), frame=frame)


def test_scoreboard_counts_only_validated_divergences_as_catches(tmp_path):
    store, frame = _store(tmp_path)
    # concordant — agreement, must NOT be a catch
    _add(store, frame, "r1", "o1", "High", "High", "concordant")
    # discordant, adjudicated toward the AI -> CATCH
    _add(store, frame, "r2", "o2", "Low", "High", "discordant", adjudicated=True, final="High")
    # discordant, adjudicated toward the human -> OVERRULED
    _add(store, frame, "r3", "o3", "Low", "High", "discordant", adjudicated=True, final="Low")
    # discordant, not yet adjudicated -> PENDING
    _add(store, frame, "r4", "o4", "Low", "High", "discordant")

    report = AgreementReportService(store).report(persist=False)
    assert len(report.model_scoreboard) == 1
    m = report.model_scoreboard[0]
    assert (m.model_id, m.model_snapshot) == ("claude-opus-4-8", "2026-05-01")
    assert m.ratings == 4
    assert m.concordant == 1
    assert m.discordant == 3
    assert m.catches == 1          # only the divergence the human adopted
    assert m.overruled == 1
    assert m.pending == 1
    assert m.catch_rate == 0.5     # 1 catch / (1 catch + 1 overruled)


def test_persist_false_writes_nothing(tmp_path):
    store, frame = _store(tmp_path)
    _add(store, frame, "r1", "o1", "Low", "High", "discordant", adjudicated=True, final="High")
    before = sorted(p.name for p in tmp_path.rglob("*"))
    report = AgreementReportService(store).report(persist=False)
    after = sorted(p.name for p in tmp_path.rglob("*"))
    assert report.model_scoreboard[0].catches == 1
    assert before == after            # read-only: no exports/, no audit file churn
