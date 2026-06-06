"""map_bootstrap: sections, exact citekey resolution, explicit outcomes, dry_run."""

from citevahti.bootstrap import MapBootstrapService
from citevahti.retrieval import StaticTextSource
from citevahti.schemas.common import ItemRef
from citevahti.state import CiteVahtiStore

GUIDELINE = """# Background
Prior work [@smith2020] and [@ghost1999] established the approach.

# Outcomes
Primary analysis used [@jones2019].
<!-- outcome: progression-free survival -->

# Unmarked
We discuss mortality and overall survival extensively in prose, but mark nothing.
"""


def _setup(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    resolver = StaticTextSource(items={
        "smith2020": ItemRef(zotero_key="K1", citekey="smith2020"),
        "jones2019": ItemRef(zotero_key="K2", citekey="jones2019"),
    })
    g = tmp_path / "guideline.md"
    g.write_text(GUIDELINE, encoding="utf-8")
    return MapBootstrapService(store, resolver), store, str(g)


def test_extracts_section_nodes(tmp_path):
    svc, _, g = _setup(tmp_path)
    rep = svc.bootstrap(g)
    assert set(rep.sections) == {"Background", "Outcomes", "Unmarked"}
    sec_ids = {n.node_id for n in rep.proposed_nodes if n.type == "section"}
    assert "section:background" in sec_ids


def test_extracts_and_resolves_citekeys(tmp_path):
    svc, _, g = _setup(tmp_path)
    rep = svc.bootstrap(g)
    assert set(rep.resolved_citekeys) == {"smith2020", "jones2019"}
    assert rep.orphan_citekeys == ["ghost1999"]        # unresolved, never invented


def test_creates_study_nodes_for_resolved_only(tmp_path):
    svc, _, g = _setup(tmp_path)
    rep = svc.bootstrap(g)
    study_ids = {n.node_id for n in rep.proposed_nodes if n.type == "study"}
    assert study_ids == {"study:smith2020", "study:jones2019"}
    assert "study:ghost1999" not in study_ids


def test_outcomes_only_from_explicit_markers(tmp_path):
    svc, _, g = _setup(tmp_path)
    rep = svc.bootstrap(g)
    assert rep.outcomes == ["progression-free survival"]
    out_ids = {n.node_id for n in rep.proposed_nodes if n.type == "outcome"}
    assert out_ids == {"outcome:progression-free-survival"}  # not "mortality"/"overall survival"


def test_dry_run_does_not_mutate_map(tmp_path):
    svc, store, g = _setup(tmp_path)
    rep = svc.bootstrap(g, dry_run=True)
    assert rep.dry_run is True and rep.written is False
    assert store.load_evidence_map().nodes == []
    assert "evidence_map.save" not in [e.event for e in store.audit.entries()]


def test_write_mutates_map_and_audits(tmp_path):
    svc, store, g = _setup(tmp_path)
    rep = svc.bootstrap(g, dry_run=False)
    assert rep.written is True and rep.audit_event_id
    emap = store.load_evidence_map()
    node_ids = {n.node_id for n in emap.nodes}
    assert {"section:background", "study:smith2020", "outcome:progression-free-survival"} <= node_ids
    assert any(l.type == "cites" for l in emap.links)
    assert store.audit.verify() is True
