"""Probe Zotero ``/api/``, Better BibTeX ``api.ready``, and CAYW ``probe=1``.

Each probe returns a :class:`ProbeResult` with ``available`` and a remediation
string when down. :class:`CapabilityReport` gates capability use:
``require(...)`` raises before any dependent operation runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..schemas.config import Endpoints
from ..util import looks_like_version
from .client import HttpClient, HttpResponse, ProbeTransportError

# localhost (not 127.0.0.1): the Zotero /api/ path checks Host: localhost:23119.
LOCALHOST_HOST = "localhost:23119"


@dataclass
class ProbeResult:
    name: str
    available: bool
    detail: str = ""
    remediation: Optional[str] = None
    version: Optional[str] = None
    # For the Zotero probe: "parsed" when a real dotted version was read,
    # "unknown" when reachable but the version could not be parsed. We never
    # emit a fabricated version.
    version_status: Optional[str] = None


def _parse_zotero_version(resp: HttpResponse) -> Optional[str]:
    """Extract the Zotero *app* version (e.g. "9.0.4"), or None.

    Only dotted version strings are accepted. The integer schema version
    (``zotero-schema-version``, e.g. "42") and the local-API version
    (``zotero-api-version``, e.g. "3") are intentionally ignored -- neither is
    the app version and must never be surfaced as one.
    """
    # ``x-zotero-version`` is the Zotero app version (server-wide header).
    candidates = [resp.headers.get("x-zotero-version"), resp.headers.get("zotero-version")]
    try:
        body = resp.json()
        if isinstance(body, dict):
            candidates.append(body.get("version"))
            candidates.append(body.get("zotero"))
    except Exception:
        pass
    for c in candidates:
        if looks_like_version(c):
            return c.strip()  # type: ignore[union-attr]
    return None


def _parse_bbt_version(resp: HttpResponse) -> Optional[str]:
    """Extract the Better BibTeX *add-on* version, or None.

    Only dotted version strings from a BBT-specific source are accepted. The
    ``x-zotero-version`` header is the Zotero APP version and is deliberately NOT
    used here -- conflating it with the BBT version is exactly the kind of
    mislabeling the probe must avoid. If no BBT version is exposed we report
    ``version_status="unknown"`` rather than fabricate one.
    """
    for header in ("x-better-bibtex-version", "x-zotero-better-bibtex-version"):
        if looks_like_version(resp.headers.get(header)):
            return resp.headers[header].strip()
    try:
        body = resp.json()
    except Exception:
        return None
    if isinstance(body, dict):
        # BBT's api.ready returns {"zotero": "<app>", "betterbibtex": "<bbt>"}.
        # Use ONLY the betterbibtex field -- "zotero" there is the APP version.
        result = body.get("result")
        if isinstance(result, dict):
            for key in ("betterbibtex", "BetterBibTeX", "better-bibtex"):
                if looks_like_version(result.get(key)):
                    return str(result[key]).strip()
        for key in ("version", "betterBibTeX", "better-bibtex"):
            if looks_like_version(body.get(key)):
                return str(body[key]).strip()
    return None


class CapabilityUnavailable(Exception):
    code = "capability_unavailable"


def probe_zotero_api(client: HttpClient, endpoints: Endpoints) -> ProbeResult:
    """GET /api/ (read-only/GET-only). Reads the running Zotero version."""
    name = "zotero_api"
    remediation = (
        "Start Zotero 9.x (macOS) and ensure the local HTTP API is enabled "
        "(Settings -> Advanced -> Allow other applications on this computer to "
        "communicate with Zotero). The /api/ endpoint is read-only/GET-only."
    )
    try:
        resp = client.get(endpoints.zotero_api, headers={"Host": LOCALHOST_HOST})
    except ProbeTransportError as exc:
        return ProbeResult(name, False, f"unreachable: {exc}", remediation)
    if resp.status_code != 200:
        return ProbeResult(name, False, f"HTTP {resp.status_code}", remediation)
    version = _parse_zotero_version(resp)
    if version is None:
        return ProbeResult(
            name, True, "reachable (version unparsed)",
            remediation=("Zotero responded, but version could not be parsed from "
                         "the local API response."),
            version=None, version_status="unknown",
        )
    return ProbeResult(name, True, "reachable", version=version, version_status="parsed")


def probe_bbt_ready(client: HttpClient, endpoints: Endpoints) -> ProbeResult:
    """POST better-bibtex/json-rpc method api.ready."""
    name = "bbt_ready"
    remediation = (
        "Install/enable the Better BibTeX add-on in Zotero. It exposes the "
        "JSON-RPC endpoint at /better-bibtex/json-rpc."
    )
    payload = {"jsonrpc": "2.0", "method": "api.ready", "params": [], "id": 1}
    try:
        resp = client.post(endpoints.bbt_jsonrpc, json=payload,
                           headers={"Host": LOCALHOST_HOST,
                                    "Content-Type": "application/json"})
    except ProbeTransportError as exc:
        return ProbeResult(name, False, f"unreachable: {exc}", remediation)
    if resp.status_code != 200:
        return ProbeResult(name, False, f"HTTP {resp.status_code}", remediation)
    try:
        body = resp.json()
    except Exception:
        return ProbeResult(name, False, "non-JSON response", remediation)
    if isinstance(body, dict) and body.get("error"):
        return ProbeResult(name, False, f"api.ready error: {body['error']!r}", remediation)
    result = body.get("result") if isinstance(body, dict) else None
    # api.ready returns True OR a readiness/version dict; both mean ready.
    ready = result is True or (isinstance(result, dict) and bool(result))
    if ready:
        version = _parse_bbt_version(resp)
        detail = "api.ready" + (f" (bbt {version})" if version else " (version unexposed)")
        return ProbeResult(name, True, detail, version=version,
                           version_status=("parsed" if version else "unknown"))
    return ProbeResult(name, False, f"api.ready={result!r}", remediation)


def probe_cayw(client: HttpClient, endpoints: Endpoints) -> ProbeResult:
    """GET better-bibtex/cayw?probe=1 (liveness; does not pop the picker)."""
    name = "bbt_cayw"
    remediation = (
        "Better BibTeX CAYW is unavailable. Ensure Better BibTeX is up to date; "
        "the picker endpoint lives at /better-bibtex/cayw (supports format=pandoc)."
    )
    try:
        resp = client.get(endpoints.bbt_cayw, params={"probe": "1"},
                          headers={"Host": LOCALHOST_HOST})
    except ProbeTransportError as exc:
        return ProbeResult(name, False, f"unreachable: {exc}", remediation)
    if resp.status_code != 200:
        return ProbeResult(name, False, f"HTTP {resp.status_code}", remediation)
    return ProbeResult(name, True, "cayw live (probe=1)")


@dataclass
class CapabilityReport:
    results: dict[str, ProbeResult] = field(default_factory=dict)

    def available(self, name: str) -> bool:
        r = self.results.get(name)
        return bool(r and r.available)

    def require(self, name: str) -> ProbeResult:
        """Gate: raise with remediation unless the capability probed available."""
        r = self.results.get(name)
        if r is None:
            raise CapabilityUnavailable(f"capability {name!r} was never probed")
        if not r.available:
            raise CapabilityUnavailable(
                f"{name} unavailable: {r.detail}. {r.remediation or ''}".strip()
            )
        return r

    def summary(self) -> dict[str, bool]:
        return {k: v.available for k, v in self.results.items()}


def run_probes(client: HttpClient, endpoints: Optional[Endpoints] = None) -> CapabilityReport:
    """Probe all three endpoints and return a cached capability report."""
    endpoints = endpoints or Endpoints()
    results = {
        "zotero_api": probe_zotero_api(client, endpoints),
        "bbt_ready": probe_bbt_ready(client, endpoints),
        "bbt_cayw": probe_cayw(client, endpoints),
    }
    # Defense in depth: never let a non-version escape as a probed version.
    from ..validators.probe import assert_valid_probed_version

    assert_valid_probed_version(results["zotero_api"].version)
    return CapabilityReport(results=results)
