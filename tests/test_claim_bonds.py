"""Stale-bond warning: when a claim is revised, its prior evidence assessments
(claim-support ratings + final decisions) are flagged as stale — the assessment
predates the new wording. Advisory and non-destructive; nothing is invalidated.

Built on the shared ``claim_text_hash`` spec: each bond is stamped (once) with the
hash it was formed against, and ``claim_bond_status`` compares that to the claim's
current hash.
"""

import json

import pytest

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
    FakeClaimSupportRater,
)
from citevahti.claims.bonds import claim_bond_status
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore
from citevahti.util import claim_text_hash


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


def _pin(cfg):
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    cfg.ai_provenance.prompt_template_version = "v1"
    return cfg


def _setup(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(
        [ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873", title="NLST")]),
        library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return store, claim.claim_id, cand_id


def _rate(store, claim_id, cand_id, human, ai=None):
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(
        value=ai, abstained=(ai is None)) if ai is not None else None)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, human)
    if ai is not None:
        eng.support_run_ai(rec.rating_id)
    eng.support_compare(rec.rating_id)
    return rec.rating_id


# ---- the stamp: a fresh bond is anchored to the current claim text ----------
def test_support_rating_is_stamped_and_current(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    rec = store.load_support_rating(rid)
    assert rec.claim_text_hash == claim_text_hash("LDCT reduces lung-cancer mortality.")
    status = claim_bond_status(store, claim_id)
    assert status["has_stale_bonds"] is False
    assert status["bonds"] == [
        {"kind": "support_rating", "id": rid, "candidate_id": cand_id, "status": "current",
         "rated_hash": rec.claim_text_hash}]


# ---- the warning: revising the claim breaks the bond ------------------------
def test_revision_makes_the_support_bond_stale(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    svc = ClaimService(store)
    svc.propose_revision(claim_id, "Low-dose CT screening cuts all-cause mortality.")
    svc.accept_revision(claim_id)
    status = claim_bond_status(store, claim_id)
    assert status["has_stale_bonds"] is True and status["stale_count"] == 1
    assert status["bonds"][0]["status"] == "stale"
    # the stamp itself is unchanged — it records the text the bond was formed against
    assert store.load_support_rating(rid).claim_text_hash == \
        claim_text_hash("LDCT reduces lung-cancer mortality.")


def test_decision_bond_also_goes_stale(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    dec = DecisionService(store).decide(
        claim_id, cand_id, "accept", "primary endpoint supports the claim", rating_id=rid)
    assert store.load_decision(dec.decision_id).claim_text_hash == \
        claim_text_hash("LDCT reduces lung-cancer mortality.")
    svc = ClaimService(store)
    svc.propose_revision(claim_id, "Different wording entirely.")
    svc.accept_revision(claim_id)
    status = claim_bond_status(store, claim_id)
    # both the support rating and the decision are now stale
    assert status["stale_count"] == 2
    assert {b["kind"] for b in status["bonds"]} == {"support_rating", "decision"}
    assert all(b["status"] == "stale" for b in status["bonds"])


# ---- re-write doesn't whitewash: the original stamp survives a re-save -------
def test_resave_preserves_the_original_stamp(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    original = store.load_support_rating(rid).claim_text_hash
    ClaimService(store).propose_revision(claim_id, "New wording.")
    ClaimService(store).accept_revision(claim_id)
    # re-save the (now stale) rating as-is — the stamp must not jump to the new text
    store.save_support_rating(store.load_support_rating(rid))
    assert store.load_support_rating(rid).claim_text_hash == original
    assert claim_bond_status(store, claim_id)["stale_count"] == 1


# ---- legacy record (written before this feature) reads 'unknown' ------------
def test_unstamped_legacy_bond_is_unknown_not_current(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path)
    rid = _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    path = store.claim_support_dir() / f"{rid}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["claim_text_hash"] = None          # simulate a pre-feature record
    path.write_text(json.dumps(raw), encoding="utf-8")
    status = claim_bond_status(store, claim_id)
    assert status["has_stale_bonds"] is False     # never silently 'current'...
    assert status["unknown_count"] == 1
    assert status["bonds"][0]["status"] == "unknown"


# ---- report surface: row + evidence carry the stale flag (manuscript list) --
def test_report_row_flags_stale_after_revision(tmp_path):
    from citevahti.report import ClaimReportService
    store, claim_id, cand_id = _setup(tmp_path)
    _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    row = next(r for r in ClaimReportService(store).report().rows if r.claim_id == claim_id)
    assert row.has_stale_bonds is False and row.evidence[0].stale is False
    ClaimService(store).propose_revision(claim_id, "Reworded claim.")
    ClaimService(store).accept_revision(claim_id)
    row = next(r for r in ClaimReportService(store).report().rows if r.claim_id == claim_id)
    assert row.has_stale_bonds is True and row.evidence[0].stale is True


# ---- panel detail surface: per-candidate badge + claim-level flag -----------
def test_panel_detail_surfaces_stale_bond(tmp_path):
    from citevahti.panel import dispatch
    store, claim_id, cand_id = _setup(tmp_path)
    _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    root = str(tmp_path)
    _st, body = dispatch(root, "GET", f"/api/claims/{claim_id}", None)
    assert body["claim"]["has_stale_bonds"] is False
    assert body["candidates"][0]["stale_bond"] is False
    ClaimService(store).propose_revision(claim_id, "Reworded claim.")
    ClaimService(store).accept_revision(claim_id)
    _st, body = dispatch(root, "GET", f"/api/claims/{claim_id}", None)
    assert body["claim"]["has_stale_bonds"] is True
    assert body["candidates"][0]["stale_bond"] is True


# ---- agent surface: read-only, advisory ------------------------------------
def test_agent_exposes_read_only_bond_status(tmp_path):
    from citevahti import agent
    assert "claim_bond_status" in agent.TOOLS
    store, claim_id, cand_id = _setup(tmp_path)
    _rate(store, claim_id, cand_id, "directly_supports", ai="directly_supports")
    out = agent.tools.claim_bond_status(claim_id, root=str(tmp_path))
    assert out["claim_id"] == claim_id and out["has_stale_bonds"] is False
