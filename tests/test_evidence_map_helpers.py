"""Typed attachment helpers: scope enforcement, provenance, audit."""

import pytest

from citevahti.evidence import EvidenceMapService
from citevahti.schemas.common import ItemRef, Provenance
from citevahti.schemas.evidence_map import EvidenceMap, Node
from citevahti.state import CiteVahtiStore
from citevahti.validators.evidence_map import EvidenceMapError


def make_prov():
    return Provenance(tool="extract", tool_version="0.7.0",
                      ran_at="2026-06-02T00:00:00+00:00", config_hash="abc123")


def _setup(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    svc = EvidenceMapService(store)
    emap = EvidenceMap()
    svc.add_node(emap, Node(node_id="s1", type="study",
                            item=ItemRef(zotero_key="K1", citekey="smith2020")))
    return svc, store, emap


def test_adds_extracted_field_attachment_valid_scope(tmp_path):
    svc, store, emap = _setup(tmp_path)
    att = svc.add_extracted_field_attachment(
        emap, "a1", provenance=make_prov(), study_node_id="s1",
        field="sample_size", value="480")
    assert att in emap.attachments
    assert store.load_evidence_map().attachments[0].attachment_id == "a1"


def test_rejects_extracted_field_without_study_or_citekey(tmp_path):
    svc, _, emap = _setup(tmp_path)
    with pytest.raises(EvidenceMapError):
        svc.add_extracted_field_attachment(emap, "a1", provenance=make_prov(),
                                           field="sample_size", value="480")


def test_rejects_extracted_field_without_provenance(tmp_path):
    svc, _, emap = _setup(tmp_path)
    with pytest.raises(EvidenceMapError):
        svc.add_extracted_field_attachment(emap, "a1", provenance=None,
                                           study_node_id="s1", field="x", value="y")


def test_adds_verified_claim_attachment_with_claim(tmp_path):
    svc, _, emap = _setup(tmp_path)
    att = svc.add_verified_claim_attachment(emap, "c1", study_node_id="s1",
                                            claim_text="X reduces mortality")
    assert att.kind == "verified_claim" and att in emap.attachments


def test_rejects_verified_claim_without_claim(tmp_path):
    svc, _, emap = _setup(tmp_path)
    with pytest.raises(EvidenceMapError):
        svc.add_verified_claim_attachment(emap, "c1", study_node_id="s1")


def test_helper_writes_audit_event_and_verifies(tmp_path):
    svc, store, emap = _setup(tmp_path)
    svc.add_extracted_field_attachment(emap, "a1", provenance=make_prov(),
                                       study_node_id="s1", field="design",
                                       value="randomized controlled trial")
    assert "evidence_map.save" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True
