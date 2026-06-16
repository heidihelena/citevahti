"""TimestampService (issue #42): stamp the audit head, store the proof, verify it.

Read-only with respect to evidence — stamping only appends a proof file and an audit
entry; it never touches claims, ratings, or decisions. Degrades honestly: an offline or
unconfigured provider yields no proof, never a fabricated one.
"""

from __future__ import annotations

import uuid
from typing import Optional

from ..schemas.timestamp import TimestampProof
from ..util import utc_now_iso
from .provider import TimestampProvider, TimestampUnavailable


class TimestampService:
    def __init__(self, store, provider: TimestampProvider) -> None:
        self.store = store
        self.provider = provider

    def stamp(self) -> TimestampProof:
        """Timestamp the current audit head. Raises TimestampUnavailable if the provider
        can't (offline / unconfigured) — the caller reports that honestly."""
        digest = self.store.audit.last_hash()
        result = self.provider.stamp(digest)        # may raise TimestampUnavailable
        proof = TimestampProof(
            proof_id=f"ts-{uuid.uuid4().hex[:10]}", digest_hex=digest,
            provider=result.provider, gentime=result.gentime,
            token_b64=result.token_b64, created_at=utc_now_iso())
        return self.store.save_timestamp(proof)      # audits + writes atomically

    def verify(self, proof_id: str) -> dict:
        """Verify a stored proof. Independent checks:

        - **binding**: the token provably commits to the stored digest (provider-checked;
          ``None`` when the provider can't tell — e.g. RFC 3161 without ``asn1crypto``);
        - **anchored**: that digest is the hash of an entry in the *current* audit chain,
          and the chain is intact — so the proof attests to this very ledger's history.

        ``verified`` requires binding to be **established** (``True``) — an unknown binding
        (``None``) is *not* a success. ``trust`` says how far external trust goes: ``demo``
        for a local fake proof; ``binding-only`` for RFC 3161 here, because full TSA
        certificate-chain / signature validation is still a follow-up (#42).
        """
        proof = self.store.load_timestamp(proof_id)
        binding = self.provider.binds(proof.token_b64 or "", proof.digest_hex)
        intact = self.store.audit.verify()
        in_chain = any(e.hash == proof.digest_hex for e in self.store.audit.entries())
        trust = "demo" if (proof.provider or "").startswith("fake") else "binding-only"
        return {"proof_id": proof_id, "digest_hex": proof.digest_hex,
                "provider": proof.provider, "gentime": proof.gentime,
                "token_binds_digest": binding, "audit_chain_intact": intact,
                "digest_in_current_chain": in_chain, "trust": trust,
                "verified": bool(intact and in_chain and binding is True)}


def provider_for_proof(proof, *, http_post=None) -> TimestampProvider:
    """The provider that can check a *stored* proof's binding — chosen from how the proof
    was made (proof.provider), not the current config (which may have changed or be off)."""
    from .provider import FakeTimestampProvider, Rfc3161Provider

    label = proof.provider or ""
    if label.startswith("rfc3161:"):
        return Rfc3161Provider(label.split(":", 1)[1], http_post=http_post)
    return FakeTimestampProvider()


def provider_from_config(cfg, *, http_post=None) -> Optional[TimestampProvider]:
    """Build the configured provider, or None when timestamping is off (the default)."""
    from .provider import Rfc3161Provider

    ts = getattr(cfg, "timestamp", None)
    if ts is None or ts.provider == "none":
        return None
    if ts.provider == "rfc3161":
        if not ts.tsa_url:
            raise TimestampUnavailable("timestamp.provider is 'rfc3161' but no tsa_url is set")
        return Rfc3161Provider(ts.tsa_url, http_post=http_post)
    raise TimestampUnavailable(f"unknown timestamp provider {ts.provider!r}")
