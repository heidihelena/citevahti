"""Loopback panel CSRF / cross-origin hardening (audit finding #3).

The panel binds to 127.0.0.1, but a localhost HTTP server is reachable from any
website the user visits. Without guards, a "simple" cross-origin POST (which the
browser sends without a CORS preflight) could drive local mutations — an external
reviewer proved an `Origin: https://attacker.example`, `Content-Type: text/plain`
POST to /api/manuscripts/paste returned 200 and wrote a file.

Defenses (defense in depth):
  * reject a non-loopback Host header          -> defeats DNS-rebinding
  * reject a cross-origin Origin header         -> CSRF
  * require a per-session CSRF token (header)   -> positive secret check, robust even if the
                                                   Origin/Host allow-list parser has an edge case
  * require Content-Type: application/json      -> blocks the simple-request POST
The legit panel client (same loopback origin, valid token, application/json) must still work.
"""

import http.client
import json
import threading

import pytest

from citevahti.panel import make_server
from citevahti.state import CiteVahtiStore


@pytest.fixture
def panel(tmp_path):
    CiteVahtiStore(tmp_path)  # create the .citevahti ledger so the root is valid
    srv = make_server(str(tmp_path), port=0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        yield srv.server_address[1], tmp_path
    finally:
        srv.shutdown()
        th.join(timeout=2)


def _post(port, path, headers, body, host=None):
    """Raw POST with fully-controlled headers (http.client, not httpx, so we own Host)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    raw = body.encode()
    conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
    conn.putheader("Host", host or f"127.0.0.1:{port}")
    for k, v in headers.items():
        conn.putheader(k, v)
    conn.putheader("Content-Length", str(len(raw)))
    conn.endheaders()
    conn.send(raw)
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp.status


def _session_token(port):
    """Fetch the per-session CSRF token the way the legit page does (GET /api/session)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/api/session")
    resp = conn.getresponse()
    token = json.loads(resp.read())["csrf_token"]
    conn.close()
    return token


def _mds(tmp_path):
    d = tmp_path / "manuscripts"
    return sorted(p.name for p in d.glob("*.md")) if d.exists() else []


def test_exploit_is_blocked(panel):
    """The reviewer's exact exploit: cross-origin text/plain POST must NOT write."""
    port, tmp_path = panel
    payload = json.dumps({"filename": "evil", "content": "owned"})
    status = _post(port, "/api/manuscripts/paste",
                   {"Origin": "https://attacker.example", "Content-Type": "text/plain"},
                   payload)
    assert status == 403
    assert "evil.md" not in _mds(tmp_path)


def test_cross_origin_json_blocked(panel):
    port, tmp_path = panel
    payload = json.dumps({"filename": "evil2", "content": "x"})
    status = _post(port, "/api/manuscripts/paste",
                   {"Origin": "https://attacker.example", "Content-Type": "application/json"},
                   payload)
    assert status == 403
    assert "evil2.md" not in _mds(tmp_path)


def test_non_json_content_type_blocked(panel):
    # send a valid token so this isolates the Content-Type guard (otherwise the missing token
    # would 403 first); a legit-looking request with the wrong media type still gets 415.
    port, tmp_path = panel
    token = _session_token(port)
    payload = json.dumps({"filename": "evil3", "content": "x"})
    status = _post(port, "/api/manuscripts/paste",
                   {"Content-Type": "text/plain", "X-CiteVahti-Token": token}, payload)
    assert status == 415
    assert "evil3.md" not in _mds(tmp_path)


def test_non_loopback_host_blocked(panel):
    """DNS-rebinding: a request whose Host is the attacker's domain is rejected."""
    port, tmp_path = panel
    payload = json.dumps({"filename": "evil4", "content": "x"})
    status = _post(port, "/api/manuscripts/paste",
                   {"Content-Type": "application/json"}, payload, host="attacker.example")
    assert status == 403
    assert "evil4.md" not in _mds(tmp_path)


def test_missing_token_blocked(panel):
    """A same-origin application/json POST with NO session token is still rejected — the
    positive token check is independent of Origin/Host parsing."""
    port, tmp_path = panel
    payload = json.dumps({"filename": "evil5", "content": "x"})
    status = _post(port, "/api/manuscripts/paste",
                   {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"},
                   payload)
    assert status == 403
    assert "evil5.md" not in _mds(tmp_path)


def test_wrong_token_blocked(panel):
    """A guessed/forged token must not pass (constant-time compare on the server)."""
    port, tmp_path = panel
    payload = json.dumps({"filename": "evil6", "content": "x"})
    status = _post(port, "/api/manuscripts/paste",
                   {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json",
                    "X-CiteVahti-Token": "not-the-real-token"}, payload)
    assert status == 403
    assert "evil6.md" not in _mds(tmp_path)


def test_legit_same_origin_json_with_token_works(panel):
    """Same loopback origin + valid session token + application/json (what the panel client
    sends) must pass."""
    port, tmp_path = panel
    token = _session_token(port)
    payload = json.dumps({"filename": "good", "content": "# hello"})
    status = _post(port, "/api/manuscripts/paste",
                   {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json",
                    "X-CiteVahti-Token": token}, payload)
    assert status == 200
    assert "good.md" in _mds(tmp_path)
