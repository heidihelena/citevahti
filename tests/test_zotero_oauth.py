"""Zotero OAuth 1.0a connect (ADR-0005): the handshake that ends in an API key.

Deterministic — a mock transport stands in for Zotero, so we exercise the signing
and the request → authorize → access → key path with no network. Verifies:
  * the OAuth signature base string / HMAC-SHA1 are built per RFC 5849;
  * request_token and access_token parse Zotero's form-urlencoded replies;
  * the access step surfaces the API key (Zotero returns it as oauth_token_secret);
  * unconfigured client credentials are reported, not guessed.
"""

import hashlib
import hmac
from base64 import b64encode
from urllib.parse import parse_qsl, quote

import pytest

from citevahti.probe.client import HttpResponse
from citevahti.zotero.oauth import (
    ACCESS_URL,
    REQUEST_URL,
    ZoteroOAuth,
    ZoteroOAuthError,
    _signature,
    load_client_credentials,
)


class _MockZotero:
    """Pretends to be Zotero's OAuth endpoints; records the calls it received."""

    def __init__(self):
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append((url, headers))
        if url == REQUEST_URL:
            return HttpResponse(200, "oauth_token=tmptok&oauth_token_secret=tmpsecret"
                                "&oauth_callback_confirmed=true", {})
        if url == ACCESS_URL:
            # Zotero returns the durable API key as oauth_token_secret, plus userID
            return HttpResponse(200, "oauth_token=KEYID&oauth_token_secret=ZKEY123&userID=4321", {})
        return HttpResponse(404, "", {})


def test_signature_matches_rfc5849_reference():
    params = {"oauth_consumer_key": "ck", "oauth_nonce": "n", "oauth_signature_method": "HMAC-SHA1",
              "oauth_timestamp": "1000", "oauth_version": "1.0", "oauth_callback": "http://x/cb"}
    got = _signature("POST", REQUEST_URL, params, "csecret", "")
    # independent recomputation of the same base string + key
    base_params = "&".join(f"{quote(k, safe='~')}={quote(v, safe='~')}" for k, v in sorted(params.items()))
    base = "&".join(["POST", quote(REQUEST_URL, safe="~"), quote(base_params, safe="~")])
    want = b64encode(hmac.new(b"csecret&", base.encode(), hashlib.sha1).digest()).decode()
    assert got == want


def test_request_token_parses_and_signs():
    mock = _MockZotero()
    oa = ZoteroOAuth("ck", "csecret", http=mock)
    tok, sec = oa.request_token("http://127.0.0.1:8765/oauth/zotero/callback",
                                nonce="n", timestamp="1000")
    assert (tok, sec) == ("tmptok", "tmpsecret")
    # the request carried a signed OAuth Authorization header including the callback
    _, headers = mock.calls[0]
    auth = headers["Authorization"]
    assert auth.startswith("OAuth ") and "oauth_signature=" in auth
    assert "oauth_callback" in auth and "oauth_consumer_key" in auth


def test_authorize_url_carries_the_token():
    oa = ZoteroOAuth("ck", "csecret", http=_MockZotero())
    assert oa.authorize_url("tmptok") == "https://www.zotero.org/oauth/authorize?oauth_token=tmptok"


def test_access_token_yields_api_key_and_userid():
    mock = _MockZotero()
    oa = ZoteroOAuth("ck", "csecret", http=mock)
    res = oa.access_token("tmptok", "tmpsecret", "verif123", nonce="n", timestamp="1000")
    assert res == {"api_key": "ZKEY123", "user_id": "4321"}   # key comes from oauth_token_secret
    _, headers = mock.calls[-1]
    assert "oauth_verifier" in headers["Authorization"]


def test_access_token_without_key_raises():
    class _Empty(_MockZotero):
        def post(self, url, json=None, headers=None):
            return HttpResponse(200, "oauth_token=KEYID&userID=1", {})   # no secret/key
    oa = ZoteroOAuth("ck", "csecret", http=_Empty())
    with pytest.raises(ZoteroOAuthError):
        oa.access_token("t", "s", "v")


def test_request_failure_is_reported():
    class _Deny(_MockZotero):
        def post(self, url, json=None, headers=None):
            return HttpResponse(401, "invalid signature", {})
    oa = ZoteroOAuth("ck", "csecret", http=_Deny())
    with pytest.raises(ZoteroOAuthError):
        oa.request_token("http://127.0.0.1:8765/cb")


def test_client_credentials_from_env(monkeypatch):
    monkeypatch.delenv("CITEVAHTI_ZOTERO_OAUTH_CLIENT_KEY", raising=False)
    monkeypatch.delenv("CITEVAHTI_ZOTERO_OAUTH_CLIENT_SECRET", raising=False)
    assert load_client_credentials() == (None, None)
    monkeypatch.setenv("CITEVAHTI_ZOTERO_OAUTH_CLIENT_KEY", "ck")
    monkeypatch.setenv("CITEVAHTI_ZOTERO_OAUTH_CLIENT_SECRET", "cs")
    assert load_client_credentials() == ("ck", "cs")
