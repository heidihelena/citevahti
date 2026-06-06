"""assessment_tag_mirror: human/final values only, replace-on-rerate, guards."""

from citevahti.evidence import EvidenceMapService
from citevahti.schemas.common import ItemRef
from citevahti.schemas.evidence_map import Attachment, EvidenceMap, Link, Node
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
from citevahti.writeback import FakeWriteBackend, UnavailableBackend, WritebackService

from test_dual_rating import make_frame


def _ai_prov():
    return AIProvenance(provider="anthropic", model_id="claude-opus-4-8", model_snapshot="2026-05-01",
                        prompt_template_version="v1", prompt_hash="ph", config_hash="ch",
                        rated_at="2026-06-02T00:00:00+00:00")


def base(tmp_path, backend=None, tags=None):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_frame(make_frame())
    reader = (lambda zk: (tags or {}).get(zk, []))
    s = WritebackService(store, backend or FakeWriteBackend(), tag_reader=reader)
    return s, store


def add_rob(store, rid, human, ai, status, *, accepted=False, adjudicated=False, final=None):
    f = make_frame()
    ai_rating = None
    if ai is not None:
        ai_rating = AIRating(value=ai, provenance=_ai_prov(), task_type="assess")
    if accepted:
        adj = Adjudication(final_value=final, event="accepted", decided_at="2026-06-02T00:00:00+00:00")
    elif adjudicated:
        adj = Adjudication(final_value=final, event="adjudicated", decided_by="panel", rationale="r")
    else:
        adj = Adjudication()
    rec = RatingRecord(rating_id=rid, frame_id="F", frame_version="1.0.0", scheme_id="rob2",
                       subject=Subject(study_id="s1"),
                       human_rating=HumanRating(value=human, committed_at="2026-06-02T00:00:00+00:00",
                                                committed_by="rater"),
                       ai_rating=ai_rating, comparison=Comparison(status=status), adjudication=adj)
    store.save_rating(rec, frame=f)
    return rid


def grade_attachment(store):
    svc = EvidenceMapService(store)
    emap = EvidenceMap()
    svc.add_node(emap, Node(node_id="study:s1", type="study",
                            item=ItemRef(zotero_key="K1", citekey="smith2020")))
    svc.add_node(emap, Node(node_id="outcome:o1", type="outcome", label="Mortality"))
    svc.add_link(emap, Link.model_validate({"from": "study:s1", "to": "outcome:o1",
                                            "type": "about_outcome"}))
    svc.add_attachment(emap, Attachment(attachment_id="ag1", kind="assessment", scheme_kind="GRADE",
                                        outcome_node_id="outcome:o1", payload={"value": "Moderate"}))
    svc.rebuild_reverse_index(emap)
    svc.save(emap)


def test_mirrors_grade_human_only(tmp_path):
    s, store = base(tmp_path)
    grade_attachment(store)
    diff = s.assessment_tag_mirror(assessment_attachment_id="ag1")
    assert diff.structured["new_tag"] == "GRADE:Moderate" and "K1" in diff.targets


def test_mirrors_concordant_accepted(tmp_path):
    s, store = base(tmp_path)
    add_rob(store, "r1", "Low", "Low", "concordant", accepted=True, final="Low")
    diff = s.assessment_tag_mirror(rating_id="r1")
    assert diff.structured["new_tag"] == "RoB2:Low"


def test_mirrors_adjudicated_final(tmp_path):
    s, store = base(tmp_path)
    add_rob(store, "r2", "Low", "High", "discordant", adjudicated=True, final="High")
    diff = s.assessment_tag_mirror(rating_id="r2")
    assert diff.structured["new_tag"] == "RoB2:High"


def test_refuses_unadjudicated_discordant(tmp_path):
    s, store = base(tmp_path)
    add_rob(store, "r3", "Low", "High", "discordant")
    out = s.assessment_tag_mirror(rating_id="r3")
    assert out.status == "not_mirrorable" and "adjudication" in out.remediation


def test_replaces_prior_same_scheme_tag(tmp_path):
    s, store = base(tmp_path, tags={"K1": ["RoB2:High", "Keep"]})
    add_rob(store, "r1", "Low", "Low", "concordant", accepted=True, final="Low")
    diff = s.assessment_tag_mirror(rating_id="r1")
    pt = diff.structured["per_target"][0]
    assert pt["remove"] == ["RoB2:High"] and pt["add"] == ["RoB2:Low"]   # no accumulation, Keep stays


def test_dry_run_preview_has_remove_and_add(tmp_path):
    s, store = base(tmp_path, tags={"K1": ["RoB2:High"]})
    add_rob(store, "r1", "Low", "Low", "concordant", accepted=True, final="Low")
    diff = s.assessment_tag_mirror(rating_id="r1")
    assert diff.dry_run is True and diff.confirm_token
    pt = diff.structured["per_target"][0]
    assert pt["remove"] and pt["add"]


def test_confirmed_write_through_fake(tmp_path):
    s, store = base(tmp_path)
    add_rob(store, "r1", "Low", "Low", "concordant", accepted=True, final="Low")
    diff = s.assessment_tag_mirror(rating_id="r1")
    res = s.assessment_tag_mirror(rating_id="r1", dry_run=False, confirm_token=diff.confirm_token)
    assert res.applied and "zotero.write.applied" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


def test_unavailable_layer_clean_result(tmp_path):
    s, store = base(tmp_path, backend=UnavailableBackend(kind="local_addon"))
    add_rob(store, "r1", "Low", "Low", "concordant", accepted=True, final="Low")
    diff = s.assessment_tag_mirror(rating_id="r1")
    assert diff.confirm_token and diff.backend_available is False     # preview still produced
    res = s.assessment_tag_mirror(rating_id="r1", dry_run=False, confirm_token=diff.confirm_token)
    assert res.status == "unavailable" and res.error_code == "write_layer_unavailable"


def test_no_write_without_token(tmp_path):
    s, store = base(tmp_path)
    add_rob(store, "r1", "Low", "Low", "concordant", accepted=True, final="Low")
    res = s.assessment_tag_mirror(rating_id="r1", dry_run=False, confirm_token=None)
    assert res.status == "failed" and res.error_code == "missing_confirm_token"
