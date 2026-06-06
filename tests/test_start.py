"""``citevahti start`` — the one-command launcher (ADR-0007).

Contract asserted here:
  * the panel binds loopback and is reachable while ``start`` runs;
  * a browser is opened to that loopback URL (unless suppressed);
  * **stdout stays clean** — every human-facing line goes to stderr, because
    stdout is the MCP stdio protocol channel the chat client reads;
  * the panel is torn down when the (injected) MCP runner returns;
  * a missing ``mcp`` extra degrades to keeping the panel up, not a crash;
  * readiness is rendered as plain next-step prompts.
"""

import io
import socket

import httpx

from citevahti.start import readiness_lines, start
from citevahti.state import CiteVahtiStore


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Probeless:
    """A probe client that reports nothing reachable (deterministic, offline)."""

    def get(self, *a, **k):
        raise httpx.ConnectError("offline in test")


def test_start_serves_panel_opens_browser_and_keeps_stdout_clean(tmp_path, capsys):
    CiteVahtiStore(tmp_path).init()
    port = _free_port()
    opened = []
    seen_url = {}

    def fake_browser(url):
        opened.append(url)

    def fake_mcp(root):
        # The panel must be live and answering while MCP "serves".
        r = httpx.get(f"http://127.0.0.1:{port}/api/claims", timeout=5)
        seen_url["status"] = r.status_code
        return 0

    rc = start(str(tmp_path), port=port, client=_Probeless(),
               browser_opener=fake_browser, mcp_runner=fake_mcp)

    assert rc == 0
    assert opened == [f"http://127.0.0.1:{port}"]          # browser opened to loopback
    assert seen_url["status"] == 200                        # panel was live mid-run
    out = capsys.readouterr()
    assert out.out == ""                                    # stdout is the MCP channel
    assert "Panel ready" in out.err                         # guidance went to stderr


def test_start_tears_down_panel_after_mcp_returns(tmp_path):
    CiteVahtiStore(tmp_path).init()
    port = _free_port()

    start(str(tmp_path), port=port, client=_Probeless(),
          browser_opener=lambda url: None, mcp_runner=lambda root: 0,
          out=io.StringIO())

    # The port is free again: the panel was shut down, not leaked.
    s = socket.socket()
    s.bind(("127.0.0.1", port))
    s.close()


def test_start_without_mcp_extra_keeps_panel_then_stops(tmp_path):
    CiteVahtiStore(tmp_path).init()
    port = _free_port()
    err = io.StringIO()

    def no_mcp(root):
        raise RuntimeError("the 'mcp' package is required to serve")

    import citevahti.start as start_mod

    def interrupt_once():
        # Stand in for the human pressing Ctrl-C while the panel keeps serving.
        raise KeyboardInterrupt

    orig_block = start_mod._block_until_interrupt
    start_mod._block_until_interrupt = interrupt_once
    try:
        rc = start(str(tmp_path), port=port, client=_Probeless(),
                   browser_opener=lambda url: None, mcp_runner=no_mcp, out=err)
    finally:
        start_mod._block_until_interrupt = orig_block

    assert rc == 0
    text = err.getvalue()
    assert "MCP server unavailable" in text
    assert "Keeping the panel up" in text


def test_start_no_browser_flag(tmp_path):
    CiteVahtiStore(tmp_path).init()
    port = _free_port()
    opened = []

    start(str(tmp_path), port=port, open_browser=False, client=_Probeless(),
          browser_opener=lambda url: opened.append(url),
          mcp_runner=lambda root: 0, out=io.StringIO())

    assert opened == []                                     # suppressed


def test_start_refuses_nonloopback_host(tmp_path):
    CiteVahtiStore(tmp_path).init()
    called = []
    rc = start(str(tmp_path), host="0.0.0.0", client=_Probeless(),
               browser_opener=lambda url: None,
               mcp_runner=lambda root: called.append(root) or 0, out=io.StringIO())
    assert rc == 2                 # loopback invariant enforced inside start()
    assert called == []            # never reached the MCP server


def test_start_busy_port_foreign_occupant_fails_loudly(tmp_path):
    CiteVahtiStore(tmp_path).init()
    port = _free_port()
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", port))      # occupy the port with a non-panel service
    blocker.listen(1)
    called = []
    err = io.StringIO()
    try:
        rc = start(str(tmp_path), port=port, client=_Probeless(),
                   browser_opener=lambda url: None,
                   mcp_runner=lambda root: called.append(root) or 0,
                   panel_probe=lambda url: False,     # not a CiteVahti panel
                   out=err)
    finally:
        blocker.close()
    assert rc == 2
    assert called == []                                # did not start MCP
    assert "not a CiteVahti panel" in err.getvalue()


def test_start_busy_port_existing_panel_is_reused(tmp_path):
    CiteVahtiStore(tmp_path).init()
    port = _free_port()
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", port))
    blocker.listen(1)
    opened, served = [], []
    err = io.StringIO()
    try:
        rc = start(str(tmp_path), port=port, client=_Probeless(),
                   browser_opener=lambda url: opened.append(url),
                   mcp_runner=lambda root: served.append(root) or 0,
                   panel_probe=lambda url: True,       # an existing CiteVahti panel
                   out=err)
    finally:
        blocker.close()
    assert rc == 0
    assert opened == [f"http://127.0.0.1:{port}"]      # browser sent to the live panel
    assert served == [str(tmp_path)]                   # MCP still serves alongside it
    assert "reusing it" in err.getvalue()


# ---- readiness rendering -----------------------------------------------------
def test_readiness_lines_uninitialized_says_init():
    lines = readiness_lines({"project_initialized": False, "project_dir": "/x/.citevahti",
                             "zotero": {"reachable": False}, "better_bibtex": {"reachable": False},
                             "zotero_write_ready": False, "claims": None})
    assert any("citevahti init" in ln for ln in lines)
    assert any("Open Zotero" in ln for ln in lines)


def test_readiness_lines_initialized_no_claims_prompts_manuscript():
    lines = readiness_lines({"project_initialized": True, "project_dir": "/x/.citevahti",
                             "zotero": {"reachable": True}, "better_bibtex": {"reachable": True},
                             "zotero_write_ready": True,
                             "claims": {"total": 0, "needs_support": 0, "review_needed": 0}})
    assert any("run_claim_tests" in ln for ln in lines)


def test_readiness_lines_with_claims_counts_unrated():
    lines = readiness_lines({"project_initialized": True, "project_dir": "/x/.citevahti",
                             "zotero": {"reachable": True}, "better_bibtex": {"reachable": True},
                             "zotero_write_ready": True,
                             "claims": {"total": 5, "needs_support": 2, "review_needed": 1}})
    assert any("5 claims recorded" in ln and "3 still need your rating" in ln for ln in lines)
