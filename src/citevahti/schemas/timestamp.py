"""A cryptographic timestamp proof over the audit head (ADR-0001; issue #42).

Anchors the SHA-256 hash of the audit-log head to an external time source (RFC 3161 to
begin with) — the foundation for moving the ledger from tamper-evident toward externally
timestamped. Verification here establishes token↔digest binding and current-chain
anchoring; full TSA certificate-chain / signature validation is a follow-up (#42), so
RFC 3161 trust stays experimental. Only the digest is ever sent — never manuscript text,
claims, or ratings.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class TimestampProof(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proof_id: str
    digest_hex: str                      # the audit-head hash that was timestamped (sha256 hex)
    provider: str                        # "rfc3161:<tsa>" | "fake" — how it was anchored
    gentime: Optional[str] = None        # the authority's attested time (from the token)
    token_b64: Optional[str] = None      # the opaque proof (e.g. base64 RFC 3161 token)
    created_at: str = ""                 # when CiteVahti recorded it locally
    audit_event_id: Optional[str] = None  # the audit entry stamped into this file
