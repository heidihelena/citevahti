"""Revision-diff: propose -> human reviews the diff -> accept/reject.

The claim text is NEVER silently edited. An agent may *propose* a rewrite
(flagged ai, model required); only a human *accepts* it, and the change is
audited with the before/after. The pending rewrite rides on the report row so
the inline card can render it as a diff.
"""

import pytest

from citevahti.claims import ClaimService
from citevahti.report import ClaimReportService
from citevahti.state import CiteVahtiStore


def _pin(cfg):
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    cfg.ai_provenance.prompt_template_version = "v1"
    return cfg


def _store(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    s.save_config(_pin(s.load_config()))
    return s


def test_propose_does_not_change_claim_text(tmp_path):
    store = _store(tmp_path)
    svc = ClaimService(store)
    c = svc.add_claim("LDCT cuts mortality.", "effectiveness")
    out = svc.propose_revision(c.claim_id, "Low-dose CT screening reduced lung-cancer mortality.")
    assert out.proposed_revision == "Low-dose CT screening reduced lung-cancer mortality."
    assert out.proposed_revision_by == "human"
    # the live claim text is untouched until accepted
    assert store.load_claim(c.claim_id).claim_text == "LDCT cuts mortality."


def test_accept_applies_and_clears_the_pending_rewrite(tmp_path):
    store = _store(tmp_path)
    svc = ClaimService(store)
    c = svc.add_claim("Old wording.", "background")
    svc.propose_revision(c.claim_id, "New, precise wording.")
    applied = svc.accept_revision(c.claim_id)
    assert applied.claim_text == "New, precise wording."
    assert applied.proposed_revision is None and applied.proposed_revision_by is None
    assert store.load_claim(c.claim_id).claim_text == "New, precise wording."


def test_accept_refuses_stale_preview_text(tmp_path):
    store = _store(tmp_path)
    svc = ClaimService(store)
    c = svc.add_claim("Old wording.", "background")
    svc.propose_revision(c.claim_id, "First proposed wording.")
    svc.propose_revision(c.claim_id, "Second proposed wording.")
    with pytest.raises(ValueError, match="changed since it was previewed"):
        svc.accept_revision(c.claim_id, expected_text="First proposed wording.")
    claim = store.load_claim(c.claim_id)
    assert claim.claim_text == "Old wording."
    assert claim.proposed_revision == "Second proposed wording."


def test_reject_keeps_original_and_clears_pending(tmp_path):
    store = _store(tmp_path)
    svc = ClaimService(store)
    c = svc.add_claim("Keep me.", "background")
    svc.propose_revision(c.claim_id, "Discard me.")
    kept = svc.reject_revision(c.claim_id)
    assert kept.claim_text == "Keep me." and kept.proposed_revision is None


def test_accept_audits_the_change(tmp_path):
    store = _store(tmp_path)
    svc = ClaimService(store)
    c = svc.add_claim("A.", "background")
    svc.propose_revision(c.claim_id, "A, expanded.")
    svc.accept_revision(c.claim_id)
    kinds = [e.event for e in store.audit.entries()]
    assert "claim.revision_proposed" in kinds and "claim.revised" in kinds


def test_ai_proposal_requires_a_pinned_model(tmp_path):
    store = _store(tmp_path)
    svc = ClaimService(store)
    c = svc.add_claim("A claim.", "background")
    with pytest.raises(ValueError, match="extraction_model"):
        svc.propose_revision(c.claim_id, "rewrite", extracted_by="ai")
    ok = svc.propose_revision(c.claim_id, "rewrite", extracted_by="ai",
                              extraction_model="claude-opus-4-8")
    assert ok.proposed_revision_by == "ai" and ok.proposed_revision_model == "claude-opus-4-8"


def test_empty_or_identical_revision_is_refused(tmp_path):
    store = _store(tmp_path)
    svc = ClaimService(store)
    c = svc.add_claim("Same text.", "background")
    with pytest.raises(ValueError):
        svc.propose_revision(c.claim_id, "   ")
    with pytest.raises(ValueError, match="identical"):
        svc.propose_revision(c.claim_id, "Same text.")


def test_accept_without_a_proposal_is_refused(tmp_path):
    store = _store(tmp_path)
    svc = ClaimService(store)
    c = svc.add_claim("No pending rewrite.", "background")
    with pytest.raises(ValueError, match="no proposed revision"):
        svc.accept_revision(c.claim_id)


def test_report_row_carries_the_pending_revision_for_the_diff(tmp_path):
    store = _store(tmp_path)
    svc = ClaimService(store)
    c = svc.add_claim("Vague.", "background")
    svc.propose_revision(c.claim_id, "Specific.", extracted_by="ai",
                         extraction_model="claude-opus-4-8")
    row = next(r for r in ClaimReportService(store).report().rows if r.claim_id == c.claim_id)
    assert row.proposed_revision == "Specific." and row.proposed_revision_by == "ai"


# ---- agent surface: agent may propose, never accept ------------------------
def test_agent_can_propose_but_cannot_accept_a_revision(tmp_path):
    from citevahti import agent
    assert "propose_revision" in agent.TOOLS
    assert "accept_revision" not in agent.TOOLS and "reject_revision" not in agent.TOOLS
    assert "accept_revision" in agent.FORBIDDEN_AGENT_CAPABILITIES
    store = _store(tmp_path)
    c = ClaimService(store).add_claim("Agent target.", "background")
    out = agent.tools.propose_revision(c.claim_id, "Agent-suggested rewrite.", root=str(tmp_path))
    assert out["status"] == "proposed"
    claim = store.load_claim(c.claim_id)
    assert claim.proposed_revision == "Agent-suggested rewrite."
    assert claim.proposed_revision_by == "ai"          # flagged + provenance
    assert claim.claim_text == "Agent target."          # not applied


def test_cli_revision_roundtrip(tmp_path, capsys):
    from citevahti.cli import main
    store = _store(tmp_path)
    c = ClaimService(store).add_claim("CLI claim.", "background")
    main(["--root", str(tmp_path), "claim-propose-revision",
          "--claim-id", c.claim_id, "--text", "CLI claim, revised."])
    assert "not applied" in capsys.readouterr().out
    main(["--root", str(tmp_path), "claim-accept-revision", "--claim-id", c.claim_id,
          "--expected-text", "CLI claim, revised."])
    assert "revision applied" in capsys.readouterr().out
    assert store.load_claim(c.claim_id).claim_text == "CLI claim, revised."
