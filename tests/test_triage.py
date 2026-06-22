"""Risk-first triage: surface only the claims that need attention, worst-first, each
with a plain reason + a next action — so a researcher reviews the few, not all."""

from citevahti.demo import build
from citevahti.report.claim_report import ClaimReportService
from citevahti.risk import triage
from citevahti.state import CiteVahtiStore


def _triage(tmp_path):
    build(tmp_path)                       # demo: accept, caution, review_needed, await-rating, reject
    rep = ClaimReportService(CiteVahtiStore(tmp_path)).report()
    return triage(rep)


def test_triage_lists_only_claims_needing_attention(tmp_path):
    t = _triage(tmp_path)
    states = [it.state for it in t.items]
    assert "accepted" not in states                       # clean accepts are NOT surfaced
    assert "review_needed" in states                      # raters disagree IS surfaced
    assert "needs_support" in states                      # the await-rating claim IS surfaced
    assert t.clean >= 1 and t.needs_attention >= 1
    assert t.needs_attention + t.clean == sum(
        1 for r in rep_states(tmp_path) if r != "untestable")


def test_every_triage_item_has_a_reason_and_action(tmp_path):
    t = _triage(tmp_path)
    for it in t.items:
        assert it.reason and it.action                    # intellectually supportive: why + what to do


def test_triage_orders_worst_first(tmp_path):
    t = _triage(tmp_path)
    risks = [(not it.fatal, -it.risk) for it in t.items]
    assert risks == sorted(risks)                         # fatal first, then risk descending


def rep_states(tmp_path):
    return [r.state for r in ClaimReportService(CiteVahtiStore(tmp_path)).report().rows]
