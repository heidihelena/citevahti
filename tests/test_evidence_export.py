"""evidence_export: neutral tables, selection, AI labelling, flags, no mutation."""

import json
from pathlib import Path

from citevahti.corpus import CorpusItem, SnapshotService, StaticCorpusSource
from citevahti.evidence import EvidenceMapService
from citevahti.export import EvidenceExportService
from citevahti.schemas.common import ItemRef, Provenance
from citevahti.schemas.evidence_map import Attachment, EvidenceMap, Link, Node
from citevahti.schemas.rating import (
    AIProvenance,
    AIRating,
    Comparison,
    HumanRating,
    RatingRecord,
    Subject,
)
from citevahti.state import CiteVahtiStore

from test_dual_rating import make_frame


def _prov():
    return Provenance(tool="extract", tool_version="0.7.0",
                      ran_at="2026-06-02T00:00:00+00:00", config_hash="abc")


def _ai_prov():
    return AIProvenance(provider="anthropic", model_id="claude-opus-4-8",
                        model_snapshot="2026-05-01", prompt_template_version="v1",
                        prompt_hash="ph", config_hash="ch", rated_at="2026-06-02T00:00:00+00:00")


def _setup(tmp_path, snapshot=True):
    store = CiteVahtiStore(tmp_path)
    store.init()
    frame = make_frame()
    store.save_frame(frame)
    rec = RatingRecord(rating_id="r1", frame_id="F", frame_version="1.0.0", scheme_id="rob2",
                       subject=Subject(study_id="s1"),
                       human_rating=HumanRating(value="Low", committed_at="2026-06-02T00:00:00+00:00",
                                                committed_by="rater"),
                       ai_rating=AIRating(value="Some concerns", abstained=False,
                                          provenance=_ai_prov(), task_type="assess"),
                       comparison=Comparison(status="discordant"))
    store.save_rating(rec, frame=frame)

    svc = EvidenceMapService(store)
    emap = EvidenceMap()
    svc.add_node(emap, Node(node_id="study:s1", type="study",
                            item=ItemRef(zotero_key="K1", citekey="smith2020"), label="Smith 2020"))
    svc.add_node(emap, Node(node_id="outcome:o1", type="outcome", label="Mortality"))
    svc.add_link(emap, Link.model_validate({"from": "study:s1", "to": "outcome:o1",
                                            "type": "about_outcome"}))
    svc.add_attachment(emap, Attachment(attachment_id="ef1", kind="extracted_field",
                                        study_node_id="study:s1", provenance=_prov(),
                                        payload={"field": "sample_size", "value": "480",
                                                 "passage": {"location": "char:0-10"}}))
    svc.add_attachment(emap, Attachment(attachment_id="vc1", kind="verified_claim",
                                        study_node_id="study:s1", claim_text="X reduces mortality",
                                        payload={"passage": {"location": "char:5-9"}}))
    svc.add_attachment(emap, Attachment(attachment_id="as1", kind="assessment", scheme_kind="RoB2",
                                        study_node_id="study:s1", rating_id="r1",
                                        provenance=_prov(), payload={"value": "Low"}))
    svc.add_staleness_flag_attachment(emap, "sf1", citekey="smith2020", persist=False)
    svc.add_retraction_flag_attachment(emap, "rf1", citekey="smith2020", persist=False)
    svc.rebuild_reverse_index(emap)
    svc.save(emap)
    if snapshot:
        SnapshotService(store, StaticCorpusSource(
            [CorpusItem(zotero_key="K1", citekey="smith2020", title="Smith 2020",
                        doi="10.1/x", year=2020)])).snapshot(label="s")
    return store


def _read(path):
    return Path(path).read_text()


def test_exports_full_map_to_csv(tmp_path):
    store = _setup(tmp_path)
    rep = EvidenceExportService(store).export(formats=["csv"])
    assert rep.full_map is True and "csv" in rep.formats_written
    studies = next(f for f in rep.output_files if f.endswith("studies.csv"))
    assert "smith2020" in _read(studies)


def test_exports_selected_citekey_subset(tmp_path):
    store = _setup(tmp_path)
    rep = EvidenceExportService(store).export(selection={"citekeys": ["smith2020"]}, formats=["csv"])
    assert rep.full_map is False and rep.selected_citekeys == ["smith2020"]


def test_exports_selected_outcome_subset(tmp_path):
    store = _setup(tmp_path)
    rep = EvidenceExportService(store).export(selection={"outcome_ids": ["outcome:o1"]},
                                              formats=["csv"])
    assert "smith2020" in rep.selected_citekeys


def test_exports_markdown(tmp_path):
    store = _setup(tmp_path)
    rep = EvidenceExportService(store).export(formats=["markdown"])
    md = _read(next(f for f in rep.output_files if f.endswith(".md")))
    assert "Evidence export" in md and "Assessments" in md


def test_exports_csl_json_when_available(tmp_path):
    store = _setup(tmp_path, snapshot=True)
    rep = EvidenceExportService(store).export(formats=["csl-json"])
    data = json.loads(_read(rep.output_files[0]))
    item = next(i for i in data if i["id"] == "smith2020")
    assert item["title"] == "Smith 2020" and item["DOI"] == "10.1/x"


def test_warns_on_insufficient_csl(tmp_path):
    store = _setup(tmp_path, snapshot=False)
    rep = EvidenceExportService(store).export(formats=["csl-json"])
    assert any("insufficient CSL" in w for w in rep.warnings)


def test_includes_provenance_when_requested(tmp_path):
    store = _setup(tmp_path)
    rep = EvidenceExportService(store).export(formats=["csv"], include_provenance=True)
    ef = _read(next(f for f in rep.output_files if f.endswith("extracted_fields.csv")))
    assert "prov_tool" in ef and "extract" in ef


def test_excludes_ai_values_by_default(tmp_path):
    store = _setup(tmp_path)
    rep = EvidenceExportService(store).export(formats=["csv"])
    asmt = _read(next(f for f in rep.output_files if f.endswith("assessments.csv")))
    assert "ai_value" not in asmt and "Some concerns" not in asmt


def test_includes_labeled_ai_values_when_requested(tmp_path):
    store = _setup(tmp_path)
    rep = EvidenceExportService(store).export(formats=["csv"], include_ai_values=True)
    asmt = _read(next(f for f in rep.output_files if f.endswith("assessments.csv")))
    assert "ai_value" in asmt and "ai_model_id" in asmt and "Some concerns" in asmt


def test_preserves_stale_and_retraction_flags(tmp_path):
    store = _setup(tmp_path)
    rep = EvidenceExportService(store).export(formats=["csv"])
    studies = _read(next(f for f in rep.output_files if f.endswith("studies.csv")))
    assert "sf1" in studies and "rf1" in studies


def test_reports_unknown_selection_ids(tmp_path):
    store = _setup(tmp_path)
    rep = EvidenceExportService(store).export(selection={"citekeys": ["ghost"]}, formats=["csv"])
    assert any("unknown citekey" in w for w in rep.warnings)


def test_writes_audit_and_verifies(tmp_path):
    store = _setup(tmp_path)
    rep = EvidenceExportService(store).export(formats=["csv"])
    assert rep.audit_event_id is not None
    assert "export.evidence" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


def test_does_not_mutate_evidence_map(tmp_path):
    store = _setup(tmp_path)
    before = store.load_evidence_map().model_dump()
    EvidenceExportService(store).export(formats=["csv", "markdown", "csl-json"],
                                        include_ai_values=True)
    assert store.load_evidence_map().model_dump() == before
