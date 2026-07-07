"""CLI characterization smoke (ADR-0010 PR 3a — lift cli.py off 39% before any split).

Empirically frozen behaviour of every no-arg CLI command against a populated demo
ledger, through the real ``main(argv)`` entry: exit code, a real payload, and never a
traceback. This is the safety net the cli.py handler split will ride on — crude on
purpose (see the PR-0 rationale): its job is to catch an argparse/wiring/formatting
regression during the later move of ``_cmd_*`` handlers, not to test business logic
(the engine tests do that).

Two frozen exit-code classes, both deliberate:
- rc=0 — plain reads and offline-degrading probes.
- rc=1 — the report-style commands (``report``, ``claim-report``, ``test``): a ledger
  with pending/failing claims exits nonzero BY DESIGN (like pytest with failures), so
  CI can gate on citation-integrity state. A refactor that "fixes" this to 0 is a bug.

Offline: the demo ledger needs no Zotero/AI; probe-backed commands degrade honestly.
"""

from __future__ import annotations

import json

import pytest

from citevahti.cli import main
from citevahti.demo import build
from citevahti.state import CiteVahtiStore


@pytest.fixture
def demo_root(tmp_path):
    build(tmp_path)
    return str(tmp_path)


def _run(capsys, *argv) -> tuple[int, str]:
    rc = main(list(argv))
    out = capsys.readouterr().out
    assert "Traceback" not in out, out          # never a raw crash
    return rc, out


# ---- rc=0: plain reads + offline-degrading probes --------------------------------
CLEAN_EXIT = {
    "claim-list": "claim",              # lists the demo claims
    "vocabulary": "verdict",            # the shared verdict/state/phase map (JSON)
    "agent-tools": "commit_write",      # the constrained agent surface listing
    "preflight": "project_initialized", # JSON readiness snapshot
    "doctor": "next",                   # plain-language readiness + next step
    "verify-audit": "intact",           # tamper check over the hash chain
    "warehouse-status": "enabled",      # default-off warehouse state
    "txn-list": "",                     # empty ledger -> empty-but-clean listing
    "risk": "/100",                     # the risk score line
    "status": "Connections",            # capability report (offline: degraded, not dead)
    "check-update": "",                 # PyPI probe degrades honestly offline
}


@pytest.mark.parametrize("cmd", sorted(CLEAN_EXIT))
def test_no_arg_command_exits_clean(demo_root, capsys, cmd):
    rc, out = _run(capsys, "--root", demo_root, cmd)
    assert rc == 0, f"{cmd} exited {rc}:\n{out}"
    assert CLEAN_EXIT[cmd] in out, f"{cmd} lost its expected output marker:\n{out}"


# ---- rc=1: report-style commands signal pending/failing claims (BY DESIGN) -------
REPORT_EXIT_ONE = {
    "claim-report": "claim",
    "report": "claim",
    "test": "skipped",                  # the manuscript "unit test" suite tally line
}


@pytest.mark.parametrize("cmd", sorted(REPORT_EXIT_ONE))
def test_report_command_signals_pending_claims_with_exit_1(demo_root, capsys, cmd):
    rc, out = _run(capsys, "--root", demo_root, cmd)
    assert rc == 1, (f"{cmd} exited {rc} — a demo ledger with pending claims must exit 1 "
                     f"(the pytest-style signal); a refactor changing this is a regression:\n{out}")
    assert REPORT_EXIT_ONE[cmd] in out


# ---- commands needing a claim id, fed from the demo ledger ------------------------
def test_candidate_and_decision_list_for_a_demo_claim(demo_root, capsys):
    claim_id = CiteVahtiStore(demo_root).list_claims()[0]
    rc, out = _run(capsys, "--root", demo_root, "candidate-list", "--claim-id", claim_id)
    assert rc == 0 and "candidate" in out.lower()
    rc, out = _run(capsys, "--root", demo_root, "decision-list", "--claim-id", claim_id)
    assert rc == 0


# ---- JSON-mode stability for the machine-readable reads ---------------------------
def test_preflight_and_vocabulary_emit_parseable_json(demo_root, capsys):
    rc, out = _run(capsys, "--root", demo_root, "preflight")
    assert rc == 0 and isinstance(json.loads(out), dict)
    rc, out = _run(capsys, "--root", demo_root, "vocabulary")
    assert rc == 0 and isinstance(json.loads(out), dict)
