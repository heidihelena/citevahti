"""Timestamp provider seam (issue #42).

A provider takes the audit-head digest and returns an external time attestation. Only the
digest crosses the boundary. Providers degrade honestly: when offline or unconfigured they
raise ``TimestampUnavailable`` rather than fabricating a proof.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from ..util import utc_now_iso


class TimestampUnavailable(Exception):
    """The provider could not produce a timestamp (offline, unconfigured, missing dep)."""


@dataclass
class TimestampResult:
    provider: str                 # e.g. "fake" or "rfc3161:https://tsa.example/tsr"
    token_b64: str                # the opaque proof
    gentime: Optional[str] = None  # the authority's attested time, if known


@runtime_checkable
class TimestampProvider(Protocol):
    name: str

    def stamp(self, digest_hex: str) -> TimestampResult: ...

    # True if the token provably commits to ``digest_hex``; None when the provider
    # can't tell (verification deferred). Never returns True without checking.
    def binds(self, token_b64: str, digest_hex: str) -> Optional[bool]: ...


class FakeTimestampProvider:
    """Deterministic, offline provider for tests and `--dry-run`. The token encodes the
    digest so binding is fully verifiable without any network or crypto dependency."""

    name = "fake"

    def __init__(self, *, available: bool = True, gentime: Optional[str] = None) -> None:
        self._available = available
        self._gentime = gentime

    def stamp(self, digest_hex: str) -> TimestampResult:
        if not self._available:
            raise TimestampUnavailable("fake timestamp provider is offline")
        token = base64.b64encode(f"FAKE-TS:{digest_hex}".encode()).decode()
        return TimestampResult(provider="fake", token_b64=token,
                               gentime=self._gentime or utc_now_iso())

    def binds(self, token_b64: str, digest_hex: str) -> Optional[bool]:
        try:
            return base64.b64decode(token_b64).decode() == f"FAKE-TS:{digest_hex}"
        except Exception:  # noqa: BLE001
            return False


class Rfc3161Provider:
    """Real RFC 3161 Time-Stamping Authority over HTTP.

    Sends ONLY a messageImprint built from the audit-head digest and stores the returned
    token. Requires the optional ``asn1crypto`` dependency (the ``[timestamp]`` extra) and
    network reachability; without either it raises ``TimestampUnavailable`` — never a fake
    proof. Note: full token signature / certificate-chain validation is a follow-up
    (issue #42); ``binds`` checks the token's messageImprint against the digest when the
    dependency is present.
    """

    name = "rfc3161"

    def __init__(self, tsa_url: str, *, http_post=None, timeout: float = 15.0) -> None:
        self.tsa_url = tsa_url
        self._timeout = timeout
        self._http_post = http_post   # injectable for tests: (url, data, headers) -> bytes

    def _asn1(self):
        try:
            from asn1crypto import tsp  # type: ignore
            return tsp
        except Exception as exc:  # noqa: BLE001
            raise TimestampUnavailable(
                "RFC 3161 timestamping needs the optional 'asn1crypto' dependency "
                "(install the citevahti[timestamp] extra)") from exc

    def _post(self, data: bytes) -> bytes:
        if self._http_post is not None:
            return self._http_post(self.tsa_url, data,
                                   {"Content-Type": "application/timestamp-query"})
        import urllib.error
        import urllib.request
        # TODO(security): allow-list http(s) on tsa_url (config-supplied) — tracked as a follow-up.
        req = urllib.request.Request(  # noqa: S310 — scheme guard deferred (see TODO above)
            self.tsa_url, data=data, headers={"Content-Type": "application/timestamp-query"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310 — see TODO above
                return resp.read()
        except (urllib.error.URLError, OSError) as exc:
            raise TimestampUnavailable(f"TSA unreachable: {exc}") from exc

    def stamp(self, digest_hex: str) -> TimestampResult:
        tsp = self._asn1()
        # The audit head IS a SHA-256 digest, so use it directly as the messageImprint.
        req = tsp.TimeStampReq({
            "version": "v1",
            "message_imprint": {
                "hash_algorithm": {"algorithm": "sha256"},
                "hashed_message": bytes.fromhex(digest_hex),
            },
            "cert_req": True,
        })
        resp_der = self._post(req.dump())
        resp = tsp.TimeStampResp.load(resp_der)
        token = resp["time_stamp_token"]
        gentime = None
        try:
            ci = token["content"]
            tst_info = tsp.TSTInfo.load(ci["encap_content_info"]["content"].native)
            gentime = tst_info["gen_time"].native.isoformat()
        except Exception:  # noqa: BLE001 — genTime is best-effort metadata
            pass
        return TimestampResult(provider=f"rfc3161:{self.tsa_url}",
                               token_b64=base64.b64encode(resp_der).decode(), gentime=gentime)

    def binds(self, token_b64: str, digest_hex: str) -> Optional[bool]:
        try:
            tsp = self._asn1()
        except TimestampUnavailable:
            return None   # can't check without the dependency — don't claim either way
        try:
            resp = tsp.TimeStampResp.load(base64.b64decode(token_b64))
            ci = resp["time_stamp_token"]["content"]
            tst_info = tsp.TSTInfo.load(ci["encap_content_info"]["content"].native)
            return tst_info["message_imprint"]["hashed_message"].native == bytes.fromhex(digest_hex)
        except Exception:  # noqa: BLE001
            return False
