"""Opt-in cryptographic timestamping of the audit head (issue #42).

Anchors the audit-head hash to a trusted external time source so the citation-integrity
record becomes third-party-verifiable, not merely tamper-evident. Off by default; only the
digest ever leaves the machine.
"""

from .provider import (
    FakeTimestampProvider,
    Rfc3161Provider,
    TimestampProvider,
    TimestampResult,
    TimestampUnavailable,
)
from .service import TimestampService, provider_from_config

__all__ = [
    "TimestampService",
    "provider_from_config",
    "TimestampProvider",
    "TimestampResult",
    "TimestampUnavailable",
    "FakeTimestampProvider",
    "Rfc3161Provider",
]
