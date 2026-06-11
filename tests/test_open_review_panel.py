"""open_review_panel: the agent can bring up the human's rating surface — the
no-terminal install (.mcpb) runs only the bare stdio server, so without this
the claim-test prompt's rate-first step dead-ends for non-technical users."""

import socket

from citevahti import agent
from citevahti.agent import policy, tools as agent_tools
from citevahti.start import launch_panel
from citevahti.state import CiteVahtiStore


def _init(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    return s


def test_tool_is_on_the_allowed_surface():
    assert "open_review_panel" in agent.TOOLS
    assert "open_review_panel" in policy.ALLOWED_AGENT_TOOLS
    policy.assert_safe_surface(agent.TOOLS.keys())


def test_launch_panel_starts_and_result_is_serializable(tmp_path):
    _init(tmp_path)
    res = launch_panel(str(tmp_path), port=0, open_browser=False)
    try:
        assert res["status"] == "started"
        assert res["url"].startswith("http://127.0.0.1")
        assert res["browser_opened"] is False
    finally:
        if res.get("_httpd") is not None:
            res["_httpd"].shutdown()
            res["_httpd"].server_close()


def test_launch_panel_refuses_non_loopback(tmp_path):
    _init(tmp_path)
    res = launch_panel(str(tmp_path), host="0.0.0.0", open_browser=False)
    assert res["status"] == "refused_non_loopback" and res["_httpd"] is None


def test_launch_panel_reports_foreign_port_honestly(tmp_path):
    _init(tmp_path)
    # Occupy a port with a non-CiteVahti socket; the probe must say "conflict",
    # never pretend the human has a rating surface.
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    try:
        res = launch_panel(str(tmp_path), port=port, open_browser=False,
                           panel_probe=lambda url: False)
        assert res["status"] == "port_conflict" and res["_httpd"] is None
    finally:
        blocker.close()


def test_agent_tool_strips_handle_and_adds_message(tmp_path, monkeypatch):
    _init(tmp_path)
    opened = {}

    def fake_launch(root, *, port, open_browser):
        opened["args"] = (root, port, open_browser)
        return {"status": "started", "url": f"http://127.0.0.1:{port}",
                "browser_opened": open_browser, "_httpd": object()}
    import citevahti.start as start_mod
    monkeypatch.setattr(start_mod, "launch_panel", fake_launch)
    res = agent_tools.open_review_panel(port=8770, root=str(tmp_path))
    assert "_httpd" not in res                       # MCP-serializable
    assert "rate" in res["message"] or "rating" in res["message"]
    assert opened["args"] == (str(tmp_path), 8770, True)
