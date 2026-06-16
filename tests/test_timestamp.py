"""Opt-in cryptographic timestamping of the audit head (issue #42).

Offline by construction: every test uses the deterministic FakeTimestampProvider, so the
seam, storage, audit integration, and verification are covered without a network or the
optional asn1crypto dependency.
"""

import pytest

from citevahti.schemas.config import Config, TimestampConfig
from citevahti.schemas.timestamp import TimestampProof
from citevahti.state import CiteVahtiStore
from citevahti.timestamp import FakeTimestampProvider, TimestampService, TimestampUnavailable
from citevahti.timestamp.service import provider_for_proof, provider_from_config


def _store(tmp_path):
    s = CiteVahtiStore(str(tmp_path))
    s.init()
    return s


def test_stamp_records_the_current_head_and_audits_it(tmp_path):
    store = _store(tmp_path)
    head_before = store.audit.last_hash()
    proof = TimestampService(store, FakeTimestampProvider(gentime="2026-06-16T00:00:00+00:00")).stamp()
    # the proof timestamps the head as it was when stamping began
    assert proof.digest_hex == head_before
    assert proof.provider == "fake"
    assert proof.gentime == "2026-06-16T00:00:00+00:00"
    assert proof.audit_event_id                       # audit-before-write stamped the file
    assert store.list_timestamps() == [proof.proof_id]
    # stamping appended its own audit entry, so the head moved forward
    assert store.audit.last_hash() != head_before


def test_verify_confirms_binding_and_chain_anchoring(tmp_path):
    store = _store(tmp_path)
    svc = TimestampService(store, FakeTimestampProvider())
    proof = svc.stamp()
    res = svc.verify(proof.proof_id)
    assert res["token_binds_digest"] is True          # the token commits to the digest
    assert res["audit_chain_intact"] is True
    assert res["digest_in_current_chain"] is True      # the stamped head is still in the chain
    assert res["verified"] is True
    assert res["trust"] == "demo"                      # a fake proof is internally verified, not trusted


class _NoneBindingProvider:
    """An rfc3161-labelled provider that can't decide the binding (e.g. asn1crypto absent)."""

    name = "rfc3161"

    def stamp(self, digest_hex):
        from citevahti.timestamp import TimestampResult
        return TimestampResult(provider="rfc3161:https://tsa.example/tsr",
                               token_b64="opaque", gentime="2026-06-16T00:00:00+00:00")

    def binds(self, token_b64, digest_hex):
        return None


def test_unknown_binding_does_not_count_as_verified(tmp_path):
    # "could not check the token↔digest binding" must NOT become a successful verification
    store = _store(tmp_path)
    svc = TimestampService(store, _NoneBindingProvider())
    proof = svc.stamp()
    res = svc.verify(proof.proof_id)
    assert res["token_binds_digest"] is None
    assert res["audit_chain_intact"] is True and res["digest_in_current_chain"] is True
    assert res["verified"] is False                    # binding must be established (True), not None
    assert res["trust"] == "binding-only"              # rfc3161: full TSA trust still pending


def test_verify_fails_when_the_digest_is_not_in_this_ledger(tmp_path):
    # a proof for some other ledger's head must not verify against this one
    store = _store(tmp_path)
    bogus = TimestampProof(proof_id="ts-bogus", digest_hex="deadbeef" * 8,
                           provider="fake", token_b64=
                           __import__("base64").b64encode(b"FAKE-TS:" + b"deadbeef" * 8).decode(),
                           created_at="2026-06-16T00:00:00+00:00")
    store.save_timestamp(bogus)
    res = TimestampService(store, FakeTimestampProvider()).verify("ts-bogus")
    assert res["digest_in_current_chain"] is False
    assert res["verified"] is False


def test_offline_provider_writes_no_proof(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(TimestampUnavailable):
        TimestampService(store, FakeTimestampProvider(available=False)).stamp()
    assert store.list_timestamps() == []              # honest degradation: nothing fabricated


def test_provider_from_config_is_off_by_default(tmp_path):
    cfg = Config.default() if hasattr(Config, "default") else None
    if cfg is not None:
        assert provider_from_config(cfg) is None       # default: timestamping off


def test_rfc3161_config_requires_a_tsa_url():
    class _Cfg:
        timestamp = TimestampConfig(provider="rfc3161", tsa_url=None)
    with pytest.raises(TimestampUnavailable):
        provider_from_config(_Cfg())


def test_provider_for_proof_matches_how_the_proof_was_made(tmp_path):
    rfc = TimestampProof(proof_id="ts-1", digest_hex="ab" * 32,
                         provider="rfc3161:https://tsa.example/tsr", created_at="t")
    p = provider_for_proof(rfc)
    assert p.name == "rfc3161" and p.tsa_url == "https://tsa.example/tsr"
    fake = TimestampProof(proof_id="ts-2", digest_hex="ab" * 32, provider="fake", created_at="t")
    assert provider_for_proof(fake).name == "fake"
