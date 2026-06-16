"""Validate a timestamp proof's shape + audit linkage (issue #42).

Mirrors the other critical objects: the store validates before stamping the audit entry
and again after, so a persisted proof always has a well-formed digest, a provider, a
token, and a recorded audit_event_id.
"""

from __future__ import annotations

import re

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class TimestampError(Exception):
    code = "timestamp_invalid"


def validate_timestamp(proof, *, require_audit: bool = False) -> None:
    if not proof.proof_id:
        raise TimestampError("proof_id is required")
    if not (proof.digest_hex and _SHA256_HEX.match(proof.digest_hex)):
        raise TimestampError("digest_hex must be a 64-char lowercase sha256 hex string")
    if not proof.provider:
        raise TimestampError("provider is required")
    if not proof.token_b64:
        raise TimestampError("token_b64 (the proof itself) is required")
    if require_audit and not proof.audit_event_id:
        raise TimestampError("audit_event_id missing — the proof was not audit-stamped")
