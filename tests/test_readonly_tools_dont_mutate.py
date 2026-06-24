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

from citevahti import tools as engine
from citevahti.demo import build


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


def test_readonly_tools_leave_the_ledger_byte_identical(tmp_path):
    build(tmp_path)                                   # a populated demo ledger
    root = str(tmp_path)
    before = _ledger_fingerprint(tmp_path)

    # every read-only surface, exercised
    engine.claim_report(root=root)
    engine.triage(root=root)
    engine.methods_statement(root=root)
    engine.check_paragraph("Structured follow-up reduces avoidable readmissions.", root=root)

    after = _ledger_fingerprint(tmp_path)
    assert after[0] == before[0], "a read-only tool appended an audit-log entry"
    assert after[1] == before[1], "a read-only tool changed a ledger file"
