"""P0: a decision file edited outside CiteVahti (e.g. final_decision flipped to
'accept' on a does_not_support rating) must NOT read as accepted, must NOT produce a
Zotero write, and must FAIL the manuscript test — even though the audit-log chain still
validates (the chain covers the log, not the materialized state).
"""

import json

import pytest

from citevahti.demo import build
from citevahti.report.claim_report import ClaimReportService
from citevahti.state import CiteVahtiStore
from citevahti.tools import run_manuscript_tests
from citevahti.writeback import FakeWriteBackend, TransactionService
from citevahti.writeback.transaction import TransactionError


def _tamper(root, *, both_fields):
    """Flip the demo's rejected decision to 'accept' on disk; returns (claim_id, decision_id)."""
    store = CiteVahtiStore(root)
    for f in (root / ".citevahti" / "decisions").glob("dec-*.json"):
        d = json.loads(f.read_text())
        if d.get("final_decision") == "reject":
            d["final_decision"] = "accept"
            if both_fields:                       # the harder variant: also fake the support status
                d["final_support_status"] = "directly_supports"
            f.write_text(json.dumps(d, indent=2))
            return d["claim_id"], f.stem
    raise AssertionError("demo had no rejected decision to tamper")


@pytest.mark.parametrize("both_fields", [False, True])
def test_tampered_accept_is_caught_everywhere(tmp_path, both_fields):
    build(tmp_path)
    store = CiteVahtiStore(tmp_path)
    assert store.audit.verify() is True               # the log chain still validates
    claim_id, decision_id = _tamper(tmp_path, both_fields=both_fields)

    rep = ClaimReportService(store).report()
    row = next(r for r in rep.rows if r.claim_id == claim_id)
    assert row.state != "accepted"                    # not a false green
    assert row.accepted_count == 0
    assert row.inconsistent is True and row.inconsistency
    assert rep.warnings and "inconsistent" in rep.warnings[0].lower()

    # the write path refuses — no preview, no Zotero write
    with pytest.raises(TransactionError, match="inconsistent"):
        TransactionService(store, FakeWriteBackend()).commit_for_decision(decision_id, dry_run=True)

    # the manuscript test fails loudly (not a skip, not a pass)
    res = run_manuscript_tests(root=str(tmp_path))
    trow = next(t for t in res["claims"] if t["claim_id"] == claim_id)
    assert trow["status"] == "fail"
    assert any(c["name"] == "ledger_integrity" for c in trow["checks"])


def test_clean_ledger_has_no_false_positive(tmp_path):
    build(tmp_path)
    rep = ClaimReportService(CiteVahtiStore(tmp_path)).report()
    assert rep.warnings == []
    assert not any(r.inconsistent for r in rep.rows)
    # the genuinely accepted demo claims still read as accepted
    assert rep.counts["accepted"] >= 1
