"""Startup probe layer: probe-not-proof.

The expected runtime defaults (Zotero 9.x local API, Better BibTeX) are NOT
treated as confirmed capability. Startup probes each endpoint and caches the
result with a remediation string; capability is reported only after a
successful probe.
"""

from .client import HttpClient, HttpResponse, HttpxClient, ProbeTransportError
from .probe import (
    CapabilityReport,
    ProbeResult,
    probe_bbt_ready,
    probe_cayw,
    probe_zotero_api,
    run_probes,
)

__all__ = [
    "HttpClient",
    "HttpResponse",
    "HttpxClient",
    "ProbeTransportError",
    "ProbeResult",
    "CapabilityReport",
    "run_probes",
    "probe_zotero_api",
    "probe_bbt_ready",
    "probe_cayw",
]
