"""The guided orchestration commands: `doctor`, `run`, `resume`, `vocabulary`.

These are thin surfaces over the resolver (citevahti.workflow) + start; the tests
keep them read-only by stubbing the panel/MCP launch, and assert the humane output
and that `run` is resumable-by-construction (it creates the ledger if missing).
"""

import json

import citevahti.start as start_mod
from citevahti.cli import main
from citevahti.state import CiteVahtiStore


def test_doctor_on_uninitialized_project_tells_you_to_init(tmp_path, capsys):
    rc = main(["--root", str(tmp_path), "doctor"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "readiness check" in out
    assert "citevahti init" in out          # plain-language next step
    assert "What to do next" in out


def test_vocabulary_emits_the_single_verdict_source_as_json(tmp_path, capsys):
    rc = main(["--root", str(tmp_path), "vocabulary"])
    assert rc == 0
    vocab = json.loads(capsys.readouterr().out)
    assert {v["decision"] for v in vocab["verdicts"]} == \
        {"accept", "accepted_with_caution", "needs_second_review", "reject"}
    assert "rate" in vocab["phases"]


def test_run_creates_the_ledger_when_missing_then_launches(tmp_path, capsys, monkeypatch):
    launched = {}

    def fake_start(root, *, port=8765, open_browser=True, **kw):
        launched["root"] = root
        return 0

    monkeypatch.setattr(start_mod, "start", fake_start)
    rc = main(["--root", str(tmp_path), "run", "--no-browser"])
    assert rc == 0
    assert CiteVahtiStore(str(tmp_path)).exists()        # init-if-needed
    assert launched["root"] == str(tmp_path)             # then hands off to the panel launch
    assert "Opening the review panel" in capsys.readouterr().out


def test_resume_names_the_next_action_then_launches(tmp_path, capsys, monkeypatch):
    CiteVahtiStore(str(tmp_path)).init()
    monkeypatch.setattr(start_mod, "start", lambda *a, **k: 0)
    rc = main(["--root", str(tmp_path), "resume", "--no-browser"])
    assert rc == 0
    assert "Resuming" in capsys.readouterr().out
