"""agreement_report: agreement metrics, kappa rules, provenance, transparency."""

import json
from pathlib import Path

from citevahti.export import AgreementReportService
from citevahti.schemas.common import ItemRef
from citevahti.schemas.frame import Frame, Level, Outcome, Scheme, Study
from citevahti.schemas.rating import (
    AIProvenance,
    Adjudication,
    AIRating,
    Comparison,
    HumanRating,
    RatingRecord,
    Subject,
)
from citevahti.state import CiteVahtiStore

GRADE = [Level(value="High", ordinal=4), Level(value="Moderate", ordinal=3),
         Level(value="Low", ordinal=2), Level(value="Very Low", ordinal=1)]
ROBINS = [Level(value="Low", ordinal=5), Level(value="Moderate", ordinal=4),
          Level(value="Serious", ordinal=3), Level(value="Critical", ordinal=2),
          Level(value="No information", ordinal=None, missing_like=True)]
ROB2 = [Level(value="Low", ordinal=3), Level(value="Some concerns", ordinal=2),
        Level(value="High", ordinal=1)]


def make_frame(n=8):
    return Frame(frame_id="F", frame_version="1.0.0", created_at="2026-06-02T00:00:00+00:00",
                 outcomes=[Outcome(outcome_id=f"o{i}", label=f"O{i}") for i in range(1, n + 1)],
                 studies=[Study(study_id=f"s{i}", item=ItemRef(zotero_key=f"K{i}", citekey=f"c{i}"))
                          for i in range(1, n + 1)],
                 schemes=[Scheme(scheme_id="grade", kind="GRADE", unit="outcome", levels=GRADE),
                          Scheme(scheme_id="robins", kind="ROBINS-I", unit="study", levels=ROBINS),
                          Scheme(scheme_id="rob2", kind="RoB2", unit="study", levels=ROB2)])


def store_with_frame(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_frame(make_frame())
    return store


def _ai_prov():
    return AIProvenance(provider="anthropic", model_id="claude-opus-4-8",
                        model_snapshot="2026-05-01", prompt_template_version="v1",
                        prompt_hash="ph", config_hash="ch", rated_at="2026-06-02T00:00:00+00:00")


def add(store, frame, rid, scheme, subject, human, ai, status, *, abstain=False,
        adjudicated=False, final=None, task="assess"):
    ai_rating = None
    if ai is not None or abstain:
        ai_rating = AIRating(value=None if abstain else ai, abstained=abstain,
                             provenance=_ai_prov(), task_type=task)
    adj = (Adjudication(final_value=final, event="adjudicated", decided_by="panel", rationale="r")
           if adjudicated else Adjudication())
    rec = RatingRecord(
        rating_id=rid, frame_id="F", frame_version="1.0.0", scheme_id=scheme, subject=subject,
        human_rating=(HumanRating(value=human, committed_at="2026-06-02T00:00:00+00:00",
                                  committed_by="rater") if human is not None else None),
        ai_rating=ai_rating, comparison=Comparison(status=status), adjudication=adj)
    store.save_rating(rec, frame=frame)
    return rec


def out(o):
    return Subject(outcome_id=o)


def stu(s):
    return Subject(study_id=s)


def test_computes_raw_agreement(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Moderate", "Moderate", "concordant")
    add(store, f, "r2", "grade", out("o2"), "Low", "Low", "concordant")
    add(store, f, "r3", "grade", out("o3"), "High", "Low", "discordant")
    add(store, f, "r4", "grade", out("o4"), "Moderate", "High", "discordant")
    rep = AgreementReportService(store).report({"scheme_id": "grade"}, ["raw_agreement"])
    assert rep.groups[0].metrics["raw_agreement"] == 0.5


def test_cohen_kappa_nominal(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Moderate", "Moderate", "concordant")
    add(store, f, "r2", "grade", out("o2"), "Low", "Low", "concordant")
    add(store, f, "r3", "grade", out("o3"), "High", "Low", "discordant")
    rep = AgreementReportService(store).report({"scheme_id": "grade"}, ["cohen_kappa"])
    ck = rep.groups[0].metrics["cohen_kappa"]
    assert ck.get("value") is not None and "error" not in ck


def test_weighted_kappa_ordinal(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "High", "High", "concordant")
    add(store, f, "r2", "grade", out("o2"), "Low", "Moderate", "discordant")
    add(store, f, "r3", "grade", out("o3"), "Moderate", "Moderate", "concordant")
    rep = AgreementReportService(store).report({"scheme_id": "grade"}, ["weighted_kappa"])
    wk = rep.groups[0].metrics["weighted_kappa"]
    assert wk.get("weights") == "quadratic" and "value" in wk


def test_refuses_kappa_across_mixed_schemes(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Moderate", "Moderate", "concordant")
    add(store, f, "r2", "rob2", stu("s1"), "Low", "Low", "concordant")
    rep = AgreementReportService(store).report(None, ["cohen_kappa"])
    assert any("refused across mixed schemes" in w for w in rep.groups[0].warnings)
    assert "cohen_kappa" not in rep.groups[0].metrics
    # grouped by scheme -> computed
    rep2 = AgreementReportService(store).report({"group_by": ["scheme_id"]}, ["cohen_kappa"])
    assert all(g.scheme_id is not None for g in rep2.groups)


def test_excludes_human_only_from_denominator(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Moderate", "Moderate", "concordant")
    add(store, f, "r2", "grade", out("o2"), "Low", None, "human_only")
    rep = AgreementReportService(store).report({"scheme_id": "grade"}, ["raw_agreement"])
    assert rep.overall.human_only == 1 and rep.overall.comparable_pairs == 1


def test_excludes_ai_abstained_but_counts(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Moderate", "Moderate", "concordant")
    add(store, f, "r2", "grade", out("o2"), "Low", None, "ai_abstained", abstain=True)
    rep = AgreementReportService(store).report({"scheme_id": "grade"}, ["raw_agreement"])
    assert rep.overall.ai_abstained == 1 and rep.overall.comparable_pairs == 1
    assert rep.ai_provenance_summary["abstention_count"] == 1


def test_discordant_adjudicated_counted_by_original(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Low", "High", "discordant",
        adjudicated=True, final="Low")
    rep = AgreementReportService(store).report({"scheme_id": "grade"}, ["adjudication_rate"])
    assert rep.overall.disagreements == 1 and rep.overall.adjudicated == 1
    assert rep.overall.pending_adjudication == 0


def test_adjudication_rate(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Moderate", "Moderate", "concordant")
    add(store, f, "r2", "grade", out("o2"), "Low", "High", "discordant")
    add(store, f, "r3", "grade", out("o3"), "High", "Low", "discordant")
    add(store, f, "r4", "grade", out("o4"), "Low", "Low", "concordant")
    rep = AgreementReportService(store).report({"scheme_id": "grade"}, ["adjudication_rate"])
    assert rep.groups[0].metrics["adjudication_rate"]["rate"] == 0.5


def test_reports_pending_adjudications(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Low", "High", "discordant")  # not adjudicated
    rep = AgreementReportService(store).report({"scheme_id": "grade"}, ["adjudication_rate"])
    assert rep.overall.pending_adjudication == 1


def test_insufficient_variation(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    for i in range(1, 4):
        add(store, f, f"r{i}", "grade", out(f"o{i}"), "Moderate", "Moderate", "concordant")
    rep = AgreementReportService(store).report({"scheme_id": "grade"}, ["cohen_kappa"])
    assert rep.groups[0].metrics["cohen_kappa"]["error"] == "insufficient_variation"


def test_robins_no_information_excluded_from_weighted(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "robins", stu("s1"), "Low", "Low", "concordant")
    add(store, f, "r2", "robins", stu("s2"), "Serious", "Moderate", "discordant")
    add(store, f, "r3", "robins", stu("s3"), "No information", "Low", "discordant")
    rep = AgreementReportService(store).report({"scheme_id": "robins"}, ["weighted_kappa"])
    wk = rep.groups[0].metrics["weighted_kappa"]
    assert wk["excluded_missing_like"] == 1
    assert any("missing-like" in w for w in rep.groups[0].warnings)


def test_groups_by_scheme_id(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Moderate", "Moderate", "concordant")
    add(store, f, "r2", "rob2", stu("s1"), "Low", "Low", "concordant")
    rep = AgreementReportService(store).report({"group_by": ["scheme_id"]}, ["raw_agreement"])
    assert {g.scheme_id for g in rep.groups} == {"grade", "rob2"}


def test_summarizes_ai_provenance(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Moderate", "Moderate", "concordant")
    rep = AgreementReportService(store).report({"scheme_id": "grade"})
    s = rep.ai_provenance_summary
    assert s["model_ids"] == ["claude-opus-4-8"] and s["task_types"] == ["assess"]


def test_writes_outputs(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Moderate", "Moderate", "concordant")
    rep = AgreementReportService(store).report({"scheme_id": "grade"},
                                               ["raw_agreement"], ["json", "csv", "markdown"])
    assert set(rep.formats_written) == {"json", "csv", "markdown"}
    assert all(Path(f).exists() for f in rep.output_files)


def test_method_transparency_section(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Moderate", "Moderate", "concordant")
    md = AgreementReportService(store).report({"scheme_id": "grade"}).method_transparency_markdown
    for needle in ["AI role", "Blinding mode", "Abstention handling", "Adjudication rule",
                   "Human/panel final authority", "Model provenance"]:
        assert needle in md
    assert "compliance" in md.lower()  # explicitly disclaims compliance


def test_writes_audit_and_does_not_mutate_ratings(tmp_path):
    store = store_with_frame(tmp_path)
    f = make_frame()
    add(store, f, "r1", "grade", out("o1"), "Low", "High", "discordant")
    before = store.load_rating("r1").model_dump()
    rep = AgreementReportService(store).report({"scheme_id": "grade"}, ["raw_agreement"])
    assert rep.audit_event_id is not None
    assert "export.agreement" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True
    assert store.load_rating("r1").model_dump() == before
