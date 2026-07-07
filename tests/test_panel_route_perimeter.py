"""Security perimeter + route inventory, frozen (ADR-0010 §5, PR 0).

The plan is to split the panel's ~600-line ``dispatch()`` into a route table. The security
perimeter (Host check + CSRF token + Origin) lives in the HTTP handler ``do_POST``, **above**
``dispatch()`` — so ``dispatch`` is pure post-authorization routing and the split is
security-neutral *by construction*, provided two invariants hold and are enforced by CI:

  * §5a rule 1 — the mutation choke point stays above the route table: **every** POST is
    rejected without a valid per-session token, before any handler runs. Proven here by
    driving the real server against the full mutating-route list (path-independence means a
    newly-split route physically cannot skip the guard).
  * §5a rule 4 — assert the whole set, not members: the POST/GET route inventory is frozen
    from source, so a relocated or newly-added route forces a conscious update here (and, for
    a new GET, a read-only review — GET must not mutate, §5a rule 2).

This is the test ADR-0010 §5b calls for. Read-only non-mutation of GET routes is proven
separately by ``test_readonly_tools_dont_mutate.py``; this file freezes the inventory that
test's coverage rides on.

Offline: binds a loopback server on port 0.
"""

from __future__ import annotations

import http.client
import pathlib
import re
import threading

import pytest

from citevahti.panel import make_server
from citevahti.state import CiteVahtiStore

pytestmark = pytest.mark.security   # loopback CSRF / route-perimeter hardening

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src/citevahti/panel/server.py"


# ---- frozen route inventory (parsed from dispatch() in server.py) ----------------------
# A diff in either set is a route change the decomposition must account for consciously.
FROZEN_MUTATING_POSTS = {
    "/api/ai-config", "/api/atlas/contribution-preview", "/api/atlas/revoke",
    "/api/candidates/recheck-library", "/api/candidates/resolve-dois",
    "/api/candidates/scan-licenses", "/api/candidates/scan-retractions",
    "/api/candidates/unlink", "/api/chat", "/api/claim-check", "/api/claim-tests-prompt",
    "/api/claims", "/api/connect/pubmed", "/api/connect/zotero",
    "/api/connect/zotero/oauth/start", "/api/decisions", "/api/document/commit-edit",
    "/api/document/preview-edit", "/api/document/undo-edit", "/api/fs/browse",
    "/api/intake/commit", "/api/intake/preview", "/api/link", "/api/manuscripts/bind",
    "/api/manuscripts/cite-export", "/api/manuscripts/import-docx", "/api/manuscripts/paste",
    "/api/prefs/update-check", "/api/ratings/start", "/api/report/docx", "/api/report/packet",
    "/api/reveal", "/api/search", "/api/setup", "/api/test-suite", "/api/topic-screen-prompt",
    "/api/warehouse/configure", "/api/warehouse/export", "/api/warehouse/purge",
    "/api/writes/commit", "/api/writes/preview", "/api/writes/undo", "/api/zotero/evidence",
    "/api/zotero/locate",
}
FROZEN_READONLY_GETS = {
    "/api/ai-config", "/api/ai/local-models", "/api/audit/log", "/api/audit/verify",
    "/api/check-update", "/api/claims", "/api/context", "/api/draft-context",
    "/api/evidence-map", "/api/health", "/api/ledgers", "/api/manuscripts", "/api/next",
    "/api/pandoc/status", "/api/ping", "/api/prompts", "/api/report", "/api/triage",
    "/api/warehouse",
}
# Parametrized (regex) route branches inside dispatch() — frozen by COUNT so a new dynamic
# mutating route (e.g. a new /api/claims/{id}/... POST) is noticed even without a literal path.
FROZEN_DYNAMIC_POST_BRANCHES = 4
FROZEN_DYNAMIC_GET_BRANCHES = 5


def _src_posts() -> set[str]:
    """Static POST routes in BOTH forms: legacy dispatch() if-branches AND the
    _POST_ROUTES table entries (ADR-0010 panel split — the conversion must keep the
    frozen inventory identical, so both registration forms count)."""
    src = _SRC.read_text()
    branches = set(re.findall(r'method == "POST" and path == "([^"]+)"', src))
    table = set(re.findall(r'^    "([^"]+)": _post_\w+', src, re.M))
    return branches | table


def _src_gets() -> set[str]:
    """Static GET routes in BOTH forms: legacy dispatch() if-branches AND the
    _GET_ROUTES table entries (ADR-0010 panel split — the route-table conversion
    must keep the frozen inventory identical, so both registration forms count)."""
    src = _SRC.read_text()
    branches = set(re.findall(r'method == "GET" and path == "([^"]+)"', src))
    table = set(re.findall(r'^    "([^"]+)": _get_\w+', src, re.M))
    return branches | table


# ---- inventory freeze (rule 4) ---------------------------------------------------------
def test_post_route_inventory_is_frozen():
    actual = _src_posts()
    assert actual == FROZEN_MUTATING_POSTS, (
        f"POST routes changed.\n  added:   {sorted(actual - FROZEN_MUTATING_POSTS)}"
        f"\n  removed: {sorted(FROZEN_MUTATING_POSTS - actual)}")


def test_get_route_inventory_is_frozen():
    actual = _src_gets()
    assert actual == FROZEN_READONLY_GETS, (
        f"GET routes changed (a new GET must be reviewed read-only, §5a rule 2).\n"
        f"  added:   {sorted(actual - FROZEN_READONLY_GETS)}"
        f"\n  removed: {sorted(FROZEN_READONLY_GETS - actual)}")


def test_dynamic_route_branch_counts_are_frozen():
    src = _SRC.read_text()
    assert len(re.findall(r'method == "POST" and m\b', src)) == FROZEN_DYNAMIC_POST_BRANCHES
    assert len(re.findall(r'method == "GET" and m\b', src)) == FROZEN_DYNAMIC_GET_BRANCHES


# ---- the choke point: every mutation needs the token, before any handler runs (rule 1) --
@pytest.fixture
def panel(tmp_path):
    CiteVahtiStore(tmp_path)  # a valid ledger root
    srv = make_server(str(tmp_path), port=0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        yield srv.server_address[1], tmp_path
    finally:
        srv.shutdown()
        th.join(timeout=2)


def _post_no_token(port, path):
    """Same-origin application/json POST with NO CSRF token — must be rejected pre-handler."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    raw = b"{}"
    conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
    conn.putheader("Host", f"127.0.0.1:{port}")
    conn.putheader("Origin", f"http://127.0.0.1:{port}")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(len(raw)))
    conn.endheaders()
    conn.send(raw)
    status = conn.getresponse().status
    conn.close()
    return status


@pytest.mark.parametrize("path", sorted(FROZEN_MUTATING_POSTS))
def test_every_mutating_post_rejects_a_missing_token(panel, path):
    port, _ = panel
    assert _post_no_token(port, path) == 403, f"{path} served a POST with no CSRF token"


def test_dynamic_and_unknown_posts_are_also_gated(panel):
    """Path-independence: the guard is above routing, so even a dynamic claim path or a
    nonexistent path is rejected without a token — a newly-split route can't slip past."""
    port, _ = panel
    for path in ("/api/claims/anyid/decide", "/api/totally-made-up-route"):
        assert _post_no_token(port, path) == 403, f"{path} was not CSRF-gated"
