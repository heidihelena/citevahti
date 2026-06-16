"""AtlasVahti contribution: de-identification is enforced, egress never accidental."""

import pytest

from citevahti import tools
from citevahti.atlas import (
    ContributionError,
    assert_poolable,
    build_contribution_bundle,
    build_revocation,
)
from citevahti.schemas.validation_record import ValidationRecord
from citevahti.state import CiteVahtiStore
from citevahti.util import sha256_hex


def _record(**over):
    base = dict(record_id="vr-1", created_at="2026-06-16T00:00:00+00:00",
                claim_text_hash=sha256_hex("ldct reduces mortality"),
                pmid="123", human_support_rating="directly_supports",
                final_support_status="supports", final_decision="accept")
    base.update(over)
    return ValidationRecord(**base)


def _seed(tmp_path, records):
    store = CiteVahtiStore(tmp_path)
    store.init()
    for r in records:
        store.append_validation_record(r)
    return store


# ---- the de-identification guard -------------------------------------------
def test_assert_poolable_accepts_a_clean_record():
    assert_poolable(_record().model_dump())  # does not raise


def test_assert_poolable_rejects_unknown_field():
    bad = {**_record().model_dump(), "project_id": "secret-proj"}
    with pytest.raises(ContributionError):
        assert_poolable(bad)


def test_assert_poolable_rejects_claim_text_without_optin():
    rec = _record(claim_text="LDCT reduces mortality").model_dump()
    with pytest.raises(ContributionError):
        assert_poolable(rec, allow_claim_text=False)
    assert_poolable(rec, allow_claim_text=True)  # allowed under the sensitive opt-in


def test_assert_poolable_requires_the_hash():
    rec = _record().model_dump()
    rec["claim_text_hash"] = ""
    with pytest.raises(ContributionError):
        assert_poolable(rec)


# ---- bundle building (no transmission) -------------------------------------
def test_bundle_strips_claim_text_when_optin_off(tmp_path):
    _seed(tmp_path, [_record(claim_text="LDCT reduces mortality")])
    bundle = build_contribution_bundle(root=str(tmp_path), allow_claim_text=False)
    assert bundle["count"] == 1 and bundle["sensitivity"] == "de_identified"
    assert bundle["records"][0]["claim_text"] is None          # stripped, not leaked
    assert bundle["contribution_id"].startswith("contrib_")
    assert bundle["content_hash"] and bundle["consent_receipt"]["revocable"] is True


def test_bundle_keeps_claim_text_under_optin(tmp_path):
    _seed(tmp_path, [_record(claim_text="LDCT reduces mortality")])
    bundle = build_contribution_bundle(root=str(tmp_path), allow_claim_text=True)
    assert bundle["sensitivity"] == "claim_text"
    assert bundle["records"][0]["claim_text"] == "LDCT reduces mortality"


def test_bundle_id_is_stable_for_same_content(tmp_path):
    _seed(tmp_path, [_record()])
    a = build_contribution_bundle(root=str(tmp_path))
    b = build_contribution_bundle(root=str(tmp_path))
    assert a["contribution_id"] == b["contribution_id"]


def test_bundle_audits_the_preview(tmp_path):
    store = _seed(tmp_path, [_record()])
    before = len(store.audit.entries())
    build_contribution_bundle(root=str(tmp_path))
    after = CiteVahtiStore(tmp_path).audit.entries()
    last = after[-1]
    event = last["event"] if isinstance(last, dict) else last.event
    assert len(after) == before + 1 and event == "atlas.bundle_preview"


# ---- revocation -------------------------------------------------------------
def test_revocation_references_the_contribution(tmp_path):
    _seed(tmp_path, [])
    req = build_revocation("contrib_abc123", reason="withdrew consent", root=str(tmp_path))
    assert req["kind"] == "revocation" and req["contribution_id"] == "contrib_abc123"
    assert req["reason"] == "withdrew consent"


def test_revocation_requires_an_id(tmp_path):
    _seed(tmp_path, [])
    with pytest.raises(ContributionError):
        build_revocation("", root=str(tmp_path))


# ---- the warehouse opt-in toggle -------------------------------------------
def test_warehouse_configure_enables(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    assert store.load_config().validation_warehouse.enabled is False
    status = tools.warehouse_configure(enabled=True, root=str(tmp_path))
    assert status.enabled is True
    assert CiteVahtiStore(tmp_path).load_config().validation_warehouse.enabled is True
