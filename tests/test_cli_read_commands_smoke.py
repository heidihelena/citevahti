"""CLI smoke for the newer read commands (`methods`, `triage`, `check-paragraph`).

These shipped across 0.22–0.24 with engine-level tests but no coverage through the CLI
`main()` entry — so an argparse/`_safe`/formatting regression would slip past CI. This
runs each through `main(argv)` on a populated demo ledger and asserts a clean exit, real
output, and no traceback. Read-only commands: they must not need network or AI.
"""

from __future__ import annotations

import json

from citevahti.cli import main
from citevahti.demo import build


def _run(capsys, *argv) -> tuple[int, str]:
    rc = main(list(argv))
    out = capsys.readouterr().out
    assert "Traceback" not in out, out          # never a raw crash
    return rc, out


def test_cli_methods_smoke(tmp_path, capsys):
    build(tmp_path)
    rc, out = _run(capsys, "--root", str(tmp_path), "methods")
    assert rc == 0
    assert "Methods statement" in out
    assert "How the literature was found" in out          # PRISMA discovery disclosure
    assert "Flow of evidence" in out                      # PRISMA flow numbers table


def test_cli_triage_smoke_text_and_json(tmp_path, capsys):
    build(tmp_path)
    rc, out = _run(capsys, "--root", str(tmp_path), "triage")
    assert rc == 0 and "/100" in out                      # the risk score line (both branches)

    rc, out = _run(capsys, "--root", str(tmp_path), "triage", "--json")
    assert rc == 0
    payload = json.loads(out)
    assert "needs_attention" in payload and "items" in payload


def test_cli_check_paragraph_smoke(tmp_path, capsys):
    build(tmp_path)
    rc, out = _run(capsys, "--root", str(tmp_path), "check-paragraph",
                   "--text", "Structured telephone follow-up reduces avoidable readmissions.")
    assert rc == 0
    assert "sentence" in out                              # the per-sentence summary line
