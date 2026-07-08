"""Safety invariant: the read-only surfaces are *actually* read-only.

`triage`, `methods`, `check_paragraph`, and `claim_report` (added across 0.22–0.24,
after `test_agent_write_boundary.py` was written) return derived views and must never
touch the ledger — no new audit-log entry, no changed file. This locks that contract so
a future edit that makes one of them write is caught immediately. Mutating the ledger
outside the audited write path would violate the tamper-evident-audit and
preview/confirm/undo guarantees.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from citevahti import agent
from citevahti import tools as engine
from citevahti.demo import build
from citevahti.panel.server import dispatch

pytestmark = pytest.mark.security   # read-only views never mutate the ledger

# panel.json is UI state, explicitly NOT part of the audited ledger (prefs.py); opening a
# manuscript records the active one there on purpose. exports/ is the audited write path.
# The *audited* ledger is everything else.
_NON_AUDITED = ("panel.json",)


def _ledger_fingerprint(root: Path) -> tuple[int, dict]:
    """(audit-log line count, {relpath: sha256}) for every file under .citevahti/."""
    ledger = root / ".citevahti"
    audit = ledger / "audit_log.jsonl"
    n_audit = len(audit.read_text(encoding="utf-8").splitlines()) if audit.exists() else 0
    files = {}
    for p in sorted(ledger.rglob("*")):
        if p.is_file():
            files[str(p.relative_to(ledger))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return n_audit, files


def _audited_fingerprint(root: Path) -> tuple[int, dict]:
    """Like ``_ledger_fingerprint`` but excludes UI state (``panel.json``) and the
    ``exports/`` audited write path — i.e. only the audited ledger a read must never touch."""
    n_audit, files = _ledger_fingerprint(root)
    audited = {k: v for k, v in files.items()
               if k.split("/")[-1] not in _NON_AUDITED and not k.startswith("exports/")}
    return n_audit, audited


def test_readonly_tools_leave_the_ledger_byte_identical(tmp_path):
    build(tmp_path)                                   # a populated demo ledger
    root = str(tmp_path)
    before = _ledger_fingerprint(tmp_path)

    # every read-only surface, exercised
    engine.claim_report(root=root)
    engine.triage(root=root)
    engine.methods_statement(root=root)
    engine.model_advisor(root=root)
    engine.model_advisor("claude-opus-4-8", root=root)
    engine.check_paragraph("Structured follow-up reduces avoidable readmissions.", root=root)

    after = _ledger_fingerprint(tmp_path)
    assert after[0] == before[0], "a read-only tool appended an audit-log entry"
    assert after[1] == before[1], "a read-only tool changed a ledger file"


def test_panel_get_endpoints_and_agent_reads_dont_touch_the_audited_ledger(tmp_path):
    # The user-facing read surface — panel GET endpoints + read-only agent tools — must
    # not append to the audit log or change an audited state file. (panel.json UI-state
    # writes, e.g. remembering the open manuscript, are allowed and excluded.)
    build(tmp_path)
    root = str(tmp_path)
    cid = dispatch(root, "GET", "/api/claims", None)[1]["claims"][0]["claim_id"]
    mid = dispatch(root, "GET", "/api/manuscripts", None)[1]["manuscripts"][0]["manuscript_id"]
    before = _audited_fingerprint(tmp_path)

    for path in ("/api/ping", "/api/context", "/api/claims", "/api/triage", "/api/manuscripts",
                 f"/api/manuscript/{mid}", f"/api/claims/{cid}",
                 f"/api/claims/{cid}/history", "/api/next", "/api/prompts", "/api/draft-context",
                 "/api/app-update"):   # frozen-app update STATUS is read-only (inert here)
        status, _ = dispatch(root, "GET", path, None)
        assert status == 200, f"{path} -> {status}"
    for name, args in (("status", ()), ("getting_started", ()), ("verify_claims", ()),
                       ("triage", ()), ("methods", ()), ("model_advisor", ()),
                       ("claim_bond_status", (cid,))):
        if name in agent.TOOLS:
            agent.TOOLS[name](*args, root=root)

    after = _audited_fingerprint(tmp_path)
    assert after[0] == before[0], "a read surface appended an audit-log entry"
    assert after[1] == before[1], "a read surface changed an audited ledger file"
