"""Claim entity (ADR-0001 step 1): first-class, audited, mutates nothing else.

A claim records what is asserted + where + who/what extracted it. It is not a
decision, not evidence, not a citation. These tests pin the store roundtrip, the
validators (incl. the AI-needs-a-model rule), audit behavior, and that creating a
claim touches no other state (no Zotero write, no evidence map mutation).
"""

import pytest

from citevahti.claims import ClaimService
from citevahti.schemas.claim import CLAIM_TYPES, Claim
from citevahti.state import CiteVahtiStore
from citevahti.state.store import StateError
from citevahti.validators.claim import ClaimError, validate_claim


def _store(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    return s


def test_add_claim_persists_with_provenance_and_audit(tmp_path):
    store = _store(tmp_path)
    claim = ClaimService(store).add_claim(
        "Low-dose CT screening reduces lung-cancer mortality in high-risk adults.",
        "effectiveness", manuscript_location="Introduction ¶2")
    assert claim.claim_id.startswith("claim-")
    assert claim.provenance and claim.provenance.tool == "claim_add"
    assert claim.audit_event_id                       # audited before write
    # roundtrip
    loaded = store.load_claim(claim.claim_id)
    assert loaded.claim_text.startswith("Low-dose CT")
    assert loaded.claim_type == "effectiveness"
    assert loaded.manuscript_location == "Introduction ¶2"


def test_claim_write_is_audited_and_chain_verifies(tmp_path):
    store = _store(tmp_path)
    ClaimService(store).add_claim("Aspirin reduces risk X.", "risk_factor")
    events = [e.event for e in store.audit.entries()]
    assert "claim.write" in events
    assert store.audit.verify() is True


def test_list_claims_roundtrip(tmp_path):
    store = _store(tmp_path)
    svc = ClaimService(store)
    svc.add_claim("Claim A", "background")
    svc.add_claim("Claim B", "mechanism")
    assert len(svc.list_claims()) == 2
    assert set(store.list_claims()) == {c.claim_id for c in svc.list_claims()}


def test_ai_extracted_claim_requires_model(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ClaimError):
        ClaimService(store).add_claim("X causes Y.", "mechanism", extracted_by="ai")
    # with a model it is accepted
    claim = ClaimService(store).add_claim(
        "X causes Y.", "mechanism", extracted_by="ai", extraction_model="claude-opus-4-8")
    assert claim.extraction_model == "claude-opus-4-8"


def test_empty_claim_text_rejected(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ClaimError):
        ClaimService(store).add_claim("   ", "other")


def test_bad_claim_type_rejected_by_schema():
    with pytest.raises(Exception):
        Claim(claim_id="c1", claim_text="x", claim_type="not_a_real_type")


def test_validator_requires_provenance():
    bare = Claim(claim_id="c1", claim_text="x", claim_type="other")
    with pytest.raises(ClaimError):
        validate_claim(bare)


def test_load_missing_claim_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(StateError):
        store.load_claim("nope")


def test_creating_a_claim_does_not_mutate_evidence_map(tmp_path):
    store = _store(tmp_path)
    before = store.load_evidence_map().model_dump()
    ClaimService(store).add_claim("Claim", "other")
    assert store.load_evidence_map().model_dump() == before     # spine only; no evidence yet


def test_all_claim_types_accepted(tmp_path):
    store = _store(tmp_path)
    for i, t in enumerate(CLAIM_TYPES):
        c = ClaimService(store).add_claim(f"claim {i}", t)
        assert c.claim_type == t
