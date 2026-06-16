"""State store: init layout, config defaults, round-trips, lock-on-rerate."""

import pytest

from citevahti.schemas.evidence_map import (
    Attachment,
    EvidenceMap,
    Link,
    Node,
    ReverseIndexEntry,
)
from citevahti.state import CiteVahtiStore
from citevahti.state.store import StateError
from citevahti.validators.errors import HumanValueLockedError

from conftest import make_grade_rating


def test_init_creates_layout_and_defaults(tmp_path):
    store = CiteVahtiStore(tmp_path)
    cfg = store.init()
    assert store.exists()
    for sub in ("frames", "ratings", "snapshots", "intake", "prisma"):
        assert (store.dir / sub).is_dir()
    # Patch 3: GRADE primary, RoB2/ROBINS-I secondary.
    assert cfg.rating.primary_scheme.scheme_id == "grade_certainty"
    assert cfg.rating.primary_scheme.kind == "GRADE"
    assert {s.scheme_id for s in cfg.rating.secondary_schemes} == {"rob2", "robins_i"}
    # Patch 10: stored exactly "Very Low".
    assert "Very Low" in {lvl.value for lvl in cfg.rating.primary_scheme.levels}
    # Patch 1: model not pinned by default.
    assert cfg.ai_provenance.is_model_pinned() is False


def test_init_is_not_clobbering(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    with pytest.raises(StateError):
        store.init()


def test_config_roundtrip(tmp_path):
    store = CiteVahtiStore(tmp_path)
    cfg = store.init()
    loaded = store.load_config()
    assert loaded.model_dump() == cfg.model_dump()


def test_evidence_map_roundtrip_with_from_alias(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    emap = EvidenceMap(
        nodes=[Node(node_id="n1", type="study", label="Smith 2020"),
               Node(node_id="n2", type="outcome", label="Mortality")],
        links=[Link.model_validate({"from": "n1", "to": "n2", "type": "about_outcome"})],
        attachments=[Attachment(attachment_id="a1", kind="assessment", target_node_id="n1")],
        reverse_index={"smith2020": ReverseIndexEntry(study_node_id="n1",
                                                       attachment_ids=["a1"])},
    )
    store.save_evidence_map(emap)
    back = store.load_evidence_map()
    assert back.links[0].from_ == "n1"
    assert back.reverse_index["smith2020"].study_node_id == "n1"
    # serialized JSON uses the "from" alias, not "from_"
    raw = store.evidence_map_path.read_text()
    assert '"from"' in raw and '"from_"' not in raw


def test_frame_and_rating_roundtrip(tmp_path, frame):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_frame(frame)
    rec = make_grade_rating()
    store.save_rating(rec, frame=frame)
    assert store.load_rating("r1").human_rating.value == "Moderate"
    assert store.list_ratings() == ["r1"]


def test_locked_human_value_cannot_be_overwritten(tmp_path, frame):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_frame(frame)
    store.save_rating(make_grade_rating(human_value="Moderate"), frame=frame)
    with pytest.raises(HumanValueLockedError):
        store.save_rating(make_grade_rating(human_value="Low"), frame=frame)


def test_load_candidates_tolerates_unknown_future_fields(tmp_path):
    # forward-compat: a newer CiteVahti may write candidate fields this version doesn't
    # know — the read must drop them, not crash and take the whole review surface down.
    import json

    from citevahti.schemas.candidate import ClaimCandidates, ClaimPaperCandidate

    store = CiteVahtiStore(tmp_path)
    store.init()
    cc = ClaimCandidates(claim_id="c1", candidates=[
        ClaimPaperCandidate(candidate_id="cand1", claim_id="c1", pmid="123", title="T",
                            retrieval_source="pubmed")])

    # write the on-disk file directly, then inject fields a FUTURE version added at both
    # levels (bypassing save-time validation — we're simulating a newer writer)
    data = json.loads(cc.model_dump_json())
    data["future_top_level"] = {"x": 1}
    data["candidates"][0]["future_candidate_field"] = "from a newer build"
    store.candidates_dir().mkdir(parents=True, exist_ok=True)
    (store.candidates_dir() / "c1.json").write_text(json.dumps(data), encoding="utf-8")

    loaded = store.load_candidates("c1")            # must NOT raise
    assert loaded.claim_id == "c1"
    assert loaded.candidates[0].candidate_id == "cand1"
    assert loaded.candidates[0].pmid == "123"
