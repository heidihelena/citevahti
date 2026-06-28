"""A minimal HTTP client seam so probes can run against a fake in tests.

We use ``localhost`` uniformly (the Zotero ``/api/`` path checks
``Host: localhost:23119``); never mix in ``127.0.0.1``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


class ProbeTransportError(Exception):
    """Raised when the endpoint is unreachable (connection refused/timeout)."""


@dataclass
class HttpResponse:
    status_code: int
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    _json: Optional[Any] = None

    def json(self) -> Any:
        if self._json is not None:
            return self._json
        import json as _json

        return _json.loads(self.text)


@runtime_checkable
class HttpClient(Protocol):
    def get(self, url: str, headers: Optional[dict[str, str]] = None,
            params: Optional[dict[str, Any]] = None) -> HttpResponse: ...

    def post(self, url: str, json: dict[str, Any] | list[Any] | None = None,
             headers: Optional[dict[str, str]] = None) -> HttpResponse: ...

    def delete(self, url: str,
               headers: Optional[dict[str, str]] = None) -> HttpResponse: ...


class HttpxClient:
    """Default client backed by httpx, with a short timeout for liveness probes."""

    def __init__(self, timeout: float = 3.0) -> None:
        self._timeout = timeout

    def _request(self, method: str, url: str, **kwargs) -> HttpResponse:
        import httpx

        try:
            resp = httpx.request(method, url, timeout=self._timeout, **kwargs)
        except httpx.HTTPError as exc:  # connection refused, timeout, etc.
            raise ProbeTransportError(str(exc)) from exc
        return HttpResponse(
            status_code=resp.status_code,
            text=resp.text,
            headers={k.lower(): v for k, v in resp.headers.items()},
        )

    def get(self, url, headers=None, params=None) -> HttpResponse:
        return self._request("GET", url, headers=headers, params=params)

    def post(self, url, json=None, headers=None) -> HttpResponse:
        return self._request("POST", url, json=json, headers=headers)

    def delete(self, url, headers=None) -> HttpResponse:
        return self._request("DELETE", url, headers=headers)
