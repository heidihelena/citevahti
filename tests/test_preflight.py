"""preflight: one read-only JSON snapshot for the guided review flow."""

import json

from citevahti.cli import main
from citevahti.claims import ClaimService
from citevahti.state import CiteVahtiStore


def _run(root, capsys):
    assert main(["--root", str(root), "preflight"]) == 0
    return json.loads(capsys.readouterr().out)


def test_preflight_on_uninitialized_project_does_not_crash(tmp_path, capsys):
    out = _run(tmp_path, capsys)                 # no .citevahti/ yet
    assert out["project_initialized"] is False
    assert out["claims"] is None                  # nothing to report, no traceback
    assert out["zotero_write_ready"] is False
    # Zotero reachability is environment-dependent (a live local Zotero may answer);
    # assert only the shape, never the machine state.
    assert isinstance(out["zotero"]["reachable"], bool)
    assert set(out["zotero"]) == {"reachable", "version"}


def test_preflight_reports_claim_counts_once_initialized(tmp_path, capsys):
    store = CiteVahtiStore(tmp_path)
    store.init()
    ClaimService(store).add_claim("An uncited assertion.", "background")
    ClaimService(store).add_claim("Another claim.", "background")
    out = _run(tmp_path, capsys)
    assert out["project_initialized"] is True
    assert out["claims"]["total"] == 2
    assert out["claims"]["needs_support"] == 2      # no candidates yet
    assert out["claims"]["with_candidates"] == 0
