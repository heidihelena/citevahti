"""Zotero OAuth 1.0a connect (ADR-0005) — the three-legged handshake.

Zotero's OAuth flow ends in an **API key** (returned as ``oauth_token_secret``)
plus the user's ID, so it is just an *automated way to obtain the same key* the
paste flow stores — the final step hands the key to ``ZoteroConnectService``.

The CiteVahti OAuth *application* identifies the client with a **client key +
secret** registered once at https://www.zotero.org/oauth/apps. Those are read from
the environment (``CITEVAHTI_ZOTERO_OAUTH_CLIENT_KEY`` / ``…_SECRET``) and are never
embedded in the repo. The per-user request/access token secrets live only in the
panel's loopback process for the duration of one handshake.

Signing is hand-rolled HMAC-SHA1 (RFC 5849) to avoid a new dependency; it is small
and fully covered by deterministic tests with a mock transport.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from base64 import b64encode
from typing import Optional
from urllib.parse import parse_qsl, quote, urlencode

REQUEST_URL = "https://www.zotero.org/oauth/request"
AUTHORIZE_URL = "https://www.zotero.org/oauth/authorize"
ACCESS_URL = "https://www.zotero.org/oauth/access"

ENV_CLIENT_KEY = "CITEVAHTI_ZOTERO_OAUTH_CLIENT_KEY"
ENV_CLIENT_SECRET = "CITEVAHTI_ZOTERO_OAUTH_CLIENT_SECRET"


class ZoteroOAuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _q(s) -> str:
    """RFC 3986 percent-encoding (unreserved chars + ``~`` left alone)."""
    return quote(str(s), safe="~")


def _signature(method: str, url: str, oauth_params: dict, client_secret: str,
               token_secret: str = "") -> str:
    base_params = "&".join(f"{_q(k)}={_q(v)}" for k, v in sorted(oauth_params.items()))
    base = "&".join([method.upper(), _q(url), _q(base_params)])
    key = f"{_q(client_secret)}&{_q(token_secret)}".encode()
    return b64encode(hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()


def _auth_header(oauth_params: dict) -> str:
    return "OAuth " + ", ".join(f'{_q(k)}="{_q(v)}"' for k, v in sorted(oauth_params.items()))


def _base_params(client_key: str, *, nonce: Optional[str] = None,
                 timestamp: Optional[str] = None) -> dict:
    return {
        "oauth_consumer_key": client_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_version": "1.0",
    }


class ZoteroOAuth:
    """Drive the OAuth 1.0a handshake. ``http`` is injectable for tests."""

    def __init__(self, client_key: str, client_secret: str, *, http=None) -> None:
        self.client_key = client_key
        self.client_secret = client_secret
        self._http = http

    def _client(self):
        if self._http is not None:
            return self._http
        from ..probe.client import HttpxClient
        return HttpxClient(timeout=8.0)

    def _post_signed(self, url: str, oauth_params: dict, token_secret: str = ""):
        oauth_params = dict(oauth_params)
        oauth_params["oauth_signature"] = _signature("POST", url, oauth_params,
                                                     self.client_secret, token_secret)
        from ..probe.client import ProbeTransportError
        try:
            return self._client().post(url, headers={"Authorization": _auth_header(oauth_params)})
        except ProbeTransportError as exc:
            raise ZoteroOAuthError("unreachable", f"could not reach Zotero OAuth ({exc})") from exc

    # ---- step 1: temporary request token --------------------------------
    def request_token(self, callback: str, *, nonce=None, timestamp=None) -> tuple[str, str]:
        params = _base_params(self.client_key, nonce=nonce, timestamp=timestamp)
        params["oauth_callback"] = callback
        resp = self._post_signed(REQUEST_URL, params)
        if resp.status_code != 200:
            raise ZoteroOAuthError("request_failed",
                                   f"Zotero refused the request token (HTTP {resp.status_code})")
        data = dict(parse_qsl(resp.text))
        if not data.get("oauth_token") or not data.get("oauth_token_secret"):
            raise ZoteroOAuthError("bad_request_token", "no request token in Zotero's response")
        return data["oauth_token"], data["oauth_token_secret"]

    # ---- step 2: the URL the user authorizes in their browser -----------
    def authorize_url(self, oauth_token: str) -> str:
        return f"{AUTHORIZE_URL}?{urlencode({'oauth_token': oauth_token})}"

    # ---- step 3: exchange the verified token for the API key ------------
    def access_token(self, oauth_token: str, token_secret: str, verifier: str,
                     *, nonce=None, timestamp=None) -> dict:
        params = _base_params(self.client_key, nonce=nonce, timestamp=timestamp)
        params["oauth_token"] = oauth_token
        params["oauth_verifier"] = verifier
        resp = self._post_signed(ACCESS_URL, params, token_secret)
        if resp.status_code != 200:
            raise ZoteroOAuthError("access_failed",
                                   f"Zotero refused the access token (HTTP {resp.status_code})")
        data = dict(parse_qsl(resp.text))
        api_key = data.get("oauth_token_secret")    # Zotero returns the API key here
        if not api_key:
            raise ZoteroOAuthError("no_api_key", "Zotero's access response carried no API key")
        return {"api_key": api_key, "user_id": str(data["userID"]) if data.get("userID") else None}


def load_client_credentials() -> tuple[Optional[str], Optional[str]]:
    """The registered CiteVahti OAuth app's client key + secret, from the env.

    Returns ``(None, None)`` when unconfigured so callers can fall back to the
    paste-a-key flow with a helpful message instead of erroring."""
    return os.environ.get(ENV_CLIENT_KEY) or None, os.environ.get(ENV_CLIENT_SECRET) or None
