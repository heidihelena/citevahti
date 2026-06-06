"""assess: controlled-value recording, scope, vocab, dual-rating, tag-mirror, staleness."""

import pytest

from citevahti.assess import AssessmentService
from citevahti.evidence import EvidenceMapService
from citevahti.rating import RatingEngine
from citevahti.schemas.evidence_map import EvidenceMap
from citevahti.schemas.rating import Subject
from citevahti.state import CiteVahtiStore
from citevahti.validators.errors import FrameError

from test_dual_rating import make_frame


def svc(tmp_path, with_engine=False):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_frame(make_frame())
    if with_engine:
        cfg = store.load_config()
        cfg.ai_provenance.model_id = "claude-opus-4-8"
        cfg.ai_provenance.model_snapshot = "2026-05-01"
        store.save_config(cfg)
    engine = RatingEngine(store) if with_engine else None
    return AssessmentService(store, engine), store


def test_records_grade_outcome_level(tmp_path):
    s, store = svc(tmp_path)
    rec = s.assess("F", "grade", Subject(outcome_id="o1"), "Moderate")
    assert rec.status == "human_only" and rec.scheme_kind == "GRADE"
    atts = store.load_evidence_map().attachments
    assert any(a.kind == "assessment" and a.scheme_kind == "GRADE" for a in atts)


def test_rejects_grade_on_study_only(tmp_path):
    s, _ = svc(tmp_path)
    with pytest.raises(FrameError):
        s.assess("F", "grade", Subject(study_id="s1"), "Moderate")


def test_records_rob_study_level(tmp_path):
    s, _ = svc(tmp_path)
    rec = s.assess("F", "rob2", Subject(study_id="s1"), "Low")
    assert rec.status == "human_only" and rec.attachment_id


def test_records_rob_study_x_outcome(tmp_path):
    s, _ = svc(tmp_path)
    rec = s.assess("F", "rob2so", Subject(study_id="s1", outcome_id="o1"), "Some concerns")
    assert rec.attachment_id


def test_rejects_rob_outcome_only(tmp_path):
    s, _ = svc(tmp_path)
    with pytest.raises(FrameError):
        s.assess("F", "rob2", Subject(outcome_id="o1"), "Low")


def test_rejects_out_of_vocabulary_value(tmp_path):
    s, _ = svc(tmp_path)
    with pytest.raises(FrameError):
        s.assess("F", "grade", Subject(outcome_id="o1"), "Excellent")


def test_rejects_computed_sentinel_value(tmp_path):
    s, _ = svc(tmp_path)
    with pytest.raises(FrameError):
        s.assess("F", "grade", Subject(outcome_id="o1"), "COMPUTED")


def test_dual_rating_false_is_human_only(tmp_path):
    s, _ = svc(tmp_path)
    rec = s.assess("F", "grade", Subject(outcome_id="o1"), "Low", dual_rating=False)
    assert rec.status == "human_only" and rec.rating_id is None


def test_dual_rating_true_starts_workflow_without_ai(tmp_path):
    s, store = svc(tmp_path, with_engine=True)
    rec = s.assess("F", "grade", Subject(outcome_id="o1"), "Low", dual_rating=True)
    assert rec.status == "dual_rating_started" and rec.rating_id
    rating = store.load_rating(rec.rating_id)
    assert rating.human_rating.value == "Low"
    assert rating.ai_rating is None              # AI not exposed before/at human commit


def test_creates_assessment_attachment(tmp_path):
    s, store = svc(tmp_path)
    rec = s.assess("F", "grade", Subject(outcome_id="o1"), "Moderate")
    atts = {a.attachment_id for a in store.load_evidence_map().attachments}
    assert rec.attachment_id in atts


def test_tag_mirror_returns_deferred(tmp_path):
    s, _ = svc(tmp_path)
    rec = s.assess("F", "rob2", Subject(study_id="s1"), "Low", tag_mirror=True)
    assert rec.tag_mirror_status == "tag_mirror_deferred_to_step_9"


def test_stale_flags_surfaced_not_cleared(tmp_path):
    s, store = svc(tmp_path)
    emap = EvidenceMap()
    msvc = EvidenceMapService(store)
    msvc.add_staleness_flag_attachment(emap, "sf1", citekey="smith2020", persist=True)
    rec = s.assess("F", "rob2", Subject(study_id="s1"), "Low")
    assert "sf1" in rec.stale_flags
    # the stale flag is still present (not silently cleared)
    assert any(a.attachment_id == "sf1" for a in store.load_evidence_map().attachments)


def test_audit_event_and_verify(tmp_path):
    s, store = svc(tmp_path)
    rec = s.assess("F", "grade", Subject(outcome_id="o1"), "Moderate")
    assert rec.audit_event_id is not None
    assert store.audit.verify() is True
