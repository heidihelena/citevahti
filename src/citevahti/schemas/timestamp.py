"""A cryptographic timestamp proof over the audit head (ADR-0001; issue #42).

Anchors the SHA-256 hash of the audit-log head to a trusted external time source
(RFC 3161 to begin with), turning the tamper-evident ledger into a third-party-verifiable
record that this review work existed by a given time. Only the digest is ever sent —
never manuscript text, claims, or ratings.
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
