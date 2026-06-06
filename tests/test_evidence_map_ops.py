"""Evidence-map operational model: node/attachment scope, reverse index, audit."""

import pytest

from citevahti.evidence import EvidenceMapService
from citevahti.schemas.common import ItemRef, Provenance
from citevahti.schemas.evidence_map import Attachment, EvidenceMap, Link, Node, ReverseIndexEntry
from citevahti.state import CiteVahtiStore
from citevahti.validators.evidence_map import EvidenceMapError

from conftest import make_grade_rating


def make_prov():
    return Provenance(tool="extract", tool_version="0.7.0",
                      ran_at="2026-06-02T00:00:00+00:00", config_hash="abc123")


def study(node_id="s1", citekey="smith2020"):
    return Node(node_id=node_id, type="study",
                item=ItemRef(zotero_key="K1", citekey=citekey), label="Smith 2020")


def outcome(node_id="o1"):
    return Node(node_id=node_id, type="outcome", label="Mortality")


def service(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    return EvidenceMapService(store), store


# ---- nodes -----------------------------------------------------------------
def test_initializes_empty_map(tmp_path):
    svc, store = service(tmp_path)
    emap = svc.init_empty()
    assert emap.nodes == [] and emap.reverse_index == {}
    assert store.load_evidence_map().nodes == []


def test_accepts_required_node_types(tmp_path):
    svc, _ = service(tmp_path)
    emap = EvidenceMap()
    for nid, t in [("r1", "recommendation"), ("sec1", "section"),
                   ("o1", "outcome"), ("s1", "study")]:
        svc.add_node(emap, Node(node_id=nid, type=t))
    assert {n.type for n in emap.nodes} == {"recommendation", "section", "outcome", "study"}


def test_rejects_unknown_node_type(tmp_path):
    svc, _ = service(tmp_path)
    bogus = Node.model_construct(node_id="x", type="bogus")
    with pytest.raises(EvidenceMapError):
        svc.add_node(EvidenceMap(), bogus)


# ---- attachments -----------------------------------------------------------
def test_accepts_typed_attachments(tmp_path):
    svc, _ = service(tmp_path)
    emap = EvidenceMap()
    svc.add_node(emap, study())
    svc.add_node(emap, outcome())
    svc.add_attachment(emap, Attachment(attachment_id="a1", kind="extracted_field",
                                        study_node_id="s1", provenance=make_prov()))
    svc.add_attachment(emap, Attachment(attachment_id="a2", kind="assessment",
                                        scheme_kind="GRADE", outcome_node_id="o1"))
    assert {a.attachment_id for a in emap.attachments} == {"a1", "a2"}


def test_rejects_unknown_attachment_kind(tmp_path):
    svc, _ = service(tmp_path)
    emap = EvidenceMap()
    svc.add_node(emap, study())
    bad = Attachment.model_construct(attachment_id="a1", kind="bogus_kind", study_node_id="s1")
    with pytest.raises(EvidenceMapError):
        svc.add_attachment(emap, bad)


def test_extracted_field_scope(tmp_path):
    svc, _ = service(tmp_path)
    emap = EvidenceMap()
    svc.add_node(emap, study())
    # missing study ref AND citekey
    with pytest.raises(EvidenceMapError):
        svc.add_attachment(emap, Attachment(attachment_id="a1", kind="extracted_field",
                                            provenance=make_prov()))
    # missing provenance
    with pytest.raises(EvidenceMapError):
        svc.add_attachment(emap, Attachment(attachment_id="a2", kind="extracted_field",
                                            study_node_id="s1"))


def test_verified_claim_scope(tmp_path):
    svc, _ = service(tmp_path)
    emap = EvidenceMap()
    svc.add_node(emap, study())
    svc.add_attachment(emap, Attachment(attachment_id="a1", kind="verified_claim",
                                        study_node_id="s1", claim_text="X reduces Y"))
    with pytest.raises(EvidenceMapError):
        svc.add_attachment(emap, Attachment(attachment_id="a2", kind="verified_claim",
                                            study_node_id="s1"))  # no claim


def test_grade_assessment_must_be_outcome_scoped(tmp_path):
    svc, _ = service(tmp_path)
    emap = EvidenceMap()
    svc.add_node(emap, study()); svc.add_node(emap, outcome())
    svc.add_attachment(emap, Attachment(attachment_id="a1", kind="assessment",
                                        scheme_kind="GRADE", outcome_node_id="o1"))
    # GRADE with study scope -> rejected
    with pytest.raises(EvidenceMapError):
        svc.add_attachment(emap, Attachment(attachment_id="a2", kind="assessment",
                                            scheme_kind="GRADE", study_node_id="s1",
                                            outcome_node_id="o1"))


def test_rob_assessment_study_or_study_x_outcome(tmp_path):
    svc, _ = service(tmp_path)
    emap = EvidenceMap()
    svc.add_node(emap, study()); svc.add_node(emap, outcome())
    svc.add_attachment(emap, Attachment(attachment_id="a1", kind="assessment",
                                        scheme_kind="RoB2", study_node_id="s1"))
    svc.add_attachment(emap, Attachment(attachment_id="a2", kind="assessment",
                                        scheme_kind="ROBINS-I", study_node_id="s1",
                                        outcome_node_id="o1"))
    assert len(emap.attachments) == 2


def test_rejects_rob_outcome_only(tmp_path):
    svc, _ = service(tmp_path)
    emap = EvidenceMap()
    svc.add_node(emap, study()); svc.add_node(emap, outcome())
    with pytest.raises(EvidenceMapError):
        svc.add_attachment(emap, Attachment(attachment_id="a1", kind="assessment",
                                            scheme_kind="RoB2", outcome_node_id="o1"))


# ---- reverse index ---------------------------------------------------------
def _build_map_with_rating(svc, store):
    emap = EvidenceMap()
    svc.add_node(emap, study())
    svc.add_node(emap, outcome())
    svc.add_link(emap, Link.model_validate({"from": "s1", "to": "o1", "type": "about_outcome"}))
    store.save_rating(make_grade_rating(rating_id="rob_r1"))  # rating record exists
    svc.add_attachment(emap, Attachment(attachment_id="a1", kind="assessment",
                                        scheme_kind="RoB2", study_node_id="s1",
                                        rating_id="rob_r1"))
    svc.rebuild_reverse_index(emap)
    return emap


def test_builds_citekey_centered_reverse_index(tmp_path):
    svc, store = service(tmp_path)
    emap = _build_map_with_rating(svc, store)
    assert "smith2020" in emap.reverse_index
    entry = emap.reverse_index["smith2020"]
    assert entry.study_node_id == "s1"
    assert "a1" in entry.attachment_ids
    assert "o1" in entry.outcome_node_ids


def test_records_rating_ids_in_reverse_index(tmp_path):
    svc, store = service(tmp_path)
    emap = _build_map_with_rating(svc, store)
    assert emap.reverse_index["smith2020"].rating_ids == ["rob_r1"]


def test_validate_reverse_index_passes(tmp_path):
    svc, store = service(tmp_path)
    emap = _build_map_with_rating(svc, store)
    svc.validate_reverse_index(emap)        # no raise
    svc.validate(emap)                       # full validation no raise


def test_detects_broken_reverse_index_references(tmp_path):
    svc, store = service(tmp_path)
    emap = _build_map_with_rating(svc, store)
    emap.reverse_index["smith2020"].attachment_ids.append("missing_att")
    problems = svc.detect_broken_references(emap)
    assert any("missing_att" in p for p in problems)
    with pytest.raises(EvidenceMapError):
        svc.validate_reverse_index(emap)


def test_broken_rating_reference_detected(tmp_path):
    svc, store = service(tmp_path)
    emap = _build_map_with_rating(svc, store)
    emap.reverse_index["smith2020"].rating_ids.append("nonexistent_rating")
    assert any("nonexistent_rating" in p for p in svc.detect_broken_references(emap))


# ---- audit -----------------------------------------------------------------
def test_mutation_writes_audit_event_and_verifies(tmp_path):
    svc, store = service(tmp_path)
    emap = EvidenceMap()
    svc.add_node(emap, study())
    svc.add_node(emap, outcome())
    svc.rebuild_reverse_index(emap)
    svc.save(emap)
    events = [e.event for e in store.audit.entries()]
    assert "evidence_map.save" in events
    assert store.audit.verify() is True
