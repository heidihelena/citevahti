"""A thin Better BibTeX JSON-RPC client.

Used by `cite` to *resolve* citekeys against the live library. It never
generates or guesses keys: a key either resolves to an existing item or it does
not, and `cite` fails on the latter.
"""

from __future__ import annotations

from typing import Any, Optional

from ..probe.client import HttpClient, ProbeTransportError
from ..schemas.config import Endpoints

# BBT exposes a citekey-aware search over the library. We treat a key as
# resolved only on an exact citekey match in the returned items.
RESOLVE_METHOD = "item.search"


class BbtUnavailable(Exception):
    """Better BibTeX is not reachable/ready (honest degradation)."""

    code = "bbt_unavailable"


class BbtError(Exception):
    """Better BibTeX returned a JSON-RPC error."""

    code = "bbt_error"


def _extract_citekey(item: dict) -> Optional[str]:
    for field in ("citekey", "citationKey", "citation-key"):
        if item.get(field):
            return str(item[field])
    return None


class BbtClient:
    def __init__(self, http: HttpClient, endpoints: Optional[Endpoints] = None) -> None:
        self.http = http
        self.endpoints = endpoints or Endpoints()

    def jsonrpc(self, method: str, params: Any) -> Any:
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        try:
            resp = self.http.post(self.endpoints.bbt_jsonrpc, json=payload,
                                  headers={"Host": "localhost:23119",
                                           "Content-Type": "application/json"})
        except ProbeTransportError as exc:
            raise BbtUnavailable(str(exc)) from exc
        if resp.status_code != 200:
            raise BbtUnavailable(f"HTTP {resp.status_code}")
        try:
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise BbtError(f"non-JSON response: {exc}") from exc
        if isinstance(body, dict) and body.get("error"):
            raise BbtError(str(body["error"]))
        return body.get("result") if isinstance(body, dict) else body

    def resolve_citekey(self, citekey: str) -> bool:
        """True iff ``citekey`` exactly matches an item known to Better BibTeX."""
        result = self.jsonrpc(RESOLVE_METHOD, [citekey])
        items = result if isinstance(result, list) else []
        return any(_extract_citekey(it) == citekey for it in items if isinstance(it, dict))
