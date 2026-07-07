"""Characterization: the CLI subcommand set is frozen (ADR-0010 PR 0).

`cli.py` is the least-tested god-file (~39%); the plan is to split its 76 handlers into
`cli/commands/*.py` with `cli.py` kept as an entry-point shim. This test freezes the
*command surface* a user (or a script) depends on, so the split cannot silently drop,
rename, or add a command. It enumerates the real argparse choices at runtime (via the
invalid-choice error argparse itself prints), so it can't drift out of sync with a
hand-maintained list — and it drives each command's ``--help`` to prove it still parses.

Offline: builds the parser only; no command body runs (``--help`` short-circuits argparse).
"""

from __future__ import annotations

import contextlib
import io
import re

import pytest

from citevahti.cli import main

# The complete `citevahti <cmd>` surface today (77). A diff here is a public CLI change.
FROZEN_COMMANDS = {
    "agent-tools", "agreement-report", "assess", "assessment-tag-mirror", "bib-sync",
    "candidate-list", "check-paragraph", "check-update", "cite-export", "claim-accept-revision",
    "claim-add", "claim-check", "claim-commit", "claim-decide", "claim-link-candidates",
    "claim-list", "claim-propose-revision", "claim-reject-revision", "claim-report",
    "claim-support-adjudicate", "claim-support-commit-human", "claim-support-compare",
    "claim-support-panel", "claim-support-run-ai", "claim-support-show", "claim-support-start",
    "claim-untestable", "claim-verify", "collection-add-item", "connect-zotero", "corpus-diff",
    "decision-list", "demo", "doctor", "evidence-export", "extract", "import-results", "init",
    "intake-push", "license-scan", "literature-search", "map-bootstrap", "mcp-serve", "methods",
    "note-add", "onboard", "preflight", "prisma-ledger", "probe", "rating-adjudicate",
    "rating-commit-human", "rating-compare", "rating-run-ai", "rating-start", "report", "resume",
    "retraction-scan", "risk", "run", "snapshot", "start", "status", "surveillance-refresh",
    "tag-add", "tag-remove", "test", "timestamp", "triage", "txn-list", "txn-show", "txn-undo",
    "verify-audit", "vocabulary", "warehouse-emit", "warehouse-export", "warehouse-purge",
    "warehouse-status",
}


def _actual_commands() -> set[str]:
    """The authoritative subcommand set, read from argparse's own 'invalid choice' listing."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), pytest.raises(SystemExit):
        main(["__no_such_command__"])
    m = re.search(r"choose from (.+?)\)", err.getvalue(), re.S)
    assert m, f"could not parse argparse choices from:\n{err.getvalue()}"
    return {c.strip().strip("'\"") for c in m.group(1).split(",")}


def test_command_set_is_exactly_frozen():
    actual = _actual_commands()
    assert actual == FROZEN_COMMANDS, (
        f"CLI command surface changed.\n  added:   {sorted(actual - FROZEN_COMMANDS)}"
        f"\n  removed: {sorted(FROZEN_COMMANDS - actual)}")


@pytest.mark.parametrize("cmd", sorted(FROZEN_COMMANDS))
def test_each_command_still_parses(cmd):
    """`citevahti <cmd> --help` must exit 0 — the subparser is registered and wired."""
    with pytest.raises(SystemExit) as exc:
        main([cmd, "--help"])
    assert exc.value.code == 0, f"{cmd} --help exited {exc.value.code}"
