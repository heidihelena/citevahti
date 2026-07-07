"""`getting_started` — the low-friction onboarding surface (better-science #3).

The state-aware "start here / what's my single next step" guide, surfaced to AI clients
(the primary distribution path). Its whole point is that it speaks to the EMPTY states a
brand-new student is in — which the risk-first `triage` cannot — and always names one
next action grounded in the actual ledger state, walking the arc:

    uninitialized -> init
    empty ledger  -> add a manuscript (paste a paragraph)
    pending claims-> review the flagged ones
    all decided   -> export the report

Offline: no network is required; the backend probe degrades to "not ready" and never
raises. Read-only is proven separately in test_readonly_tools_dont_mutate.py.
"""

from __future__ import annotations

from citevahti import agent


def test_brand_new_uninitialized_ledger_says_init(tmp_path):
    # nothing created yet — triage would have nothing to say; onboarding must
    out = agent.tools.getting_started(root=str(tmp_path))
    assert out["ready"] is False
    assert out["next"]["kind"] == "init"
    assert out["next"]["label"]                      # a concrete, imperative next step
    assert "not_initialized" in out["blockers"]


def test_initialized_but_empty_says_add_a_manuscript(tmp_path):
    agent.tools.init(root=str(tmp_path))
    out = agent.tools.getting_started(root=str(tmp_path))
    assert out["ready"] is False
    assert out["claims_total"] == 0
    assert out["next"]["kind"] == "add_claims"
    assert "paragraph" in out["next"]["label"].lower()


def test_shape_is_stable_and_json_safe(tmp_path):
    import json

    agent.tools.init(root=str(tmp_path))
    out = agent.tools.getting_started(root=str(tmp_path))
    assert set(out) == {"ready", "claims_total", "counts", "blockers", "next"}
    assert set(out["next"]) == {"kind", "label", "claim_id"}
    json.dumps(out)                                  # must carry nothing exotic


def test_never_raises_on_a_missing_project(tmp_path):
    # the onboarding entry point must be the one call that always works, even before init
    missing = tmp_path / "nope"
    out = agent.tools.getting_started(root=str(missing))
    assert out["next"]["kind"] == "init"
