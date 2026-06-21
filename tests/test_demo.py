"""The bundled zero-setup demo (`citevahti demo`).

It must build a real, engine-driven ledger that shows the FULL spread of claim
states — so the first-run experience isn't a one-note mock-up — entirely offline.
"""

from citevahti.demo import build
from citevahti.report.claim_report import ClaimReportService
from citevahti.state import CiteVahtiStore


def test_demo_builds_the_full_spread_of_states(tmp_path):
    build(tmp_path)
    rep = ClaimReportService(CiteVahtiStore(tmp_path)).report()
    assert rep.total == 5
    assert rep.counts["accepted"] == 2            # accept + accepted_with_caution
    assert rep.counts["review_needed"] == 1       # raters disagree
    assert rep.counts["needs_support"] == 1       # claim staged for the user's blind rating
    assert rep.counts["decision_recorded"] == 1   # rejected


def test_demo_writes_and_binds_the_manuscript(tmp_path):
    summary = build(tmp_path)
    assert (tmp_path / "manuscripts" / "sample-review.md").exists()
    assert summary["claims"] == 5 and summary["pending"] == 1
