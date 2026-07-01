"""``mcp_server.py``'s ``streamable-http`` sidecar path — the desktop app's agent-server
supervision, layered on top of the unchanged ``stdio`` path the Claude Desktop ``.mcpb``
uses. Never exercises the real ``SIGTERM``/``SIGINT`` handler installed by
``_serve_streamable_http`` (it calls ``os._exit(0)`` in production, which would kill the
test process) — the "runtime file is always cleared on the way out" guarantee is instead
verified via the function's own ``finally`` block, which runs the same cleanup.
"""

from __future__ import annotations

import socket

import pytest
from starlette.testclient import TestClient

from citevahti.agent import mcp_server
from citevahti import runtime_state


def test_build_server_registers_health_route_with_expected_shape():
    server = mcp_server.build_server(root="/some/project")
    client = TestClient(server.streamable_http_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["service"] == "citevahti-mcp"
    assert body["root"] == "/some/project"
    assert "version" in body


def test_build_server_default_host_is_loopback():
    server = mcp_server.build_server(root=".")
    assert server.settings.host == "127.0.0.1"


def test_main_has_no_host_flag_loopback_is_hardcoded():
    with pytest.raises(SystemExit):
        mcp_server.main(["--host", "0.0.0.0"])


def test_main_streamable_http_delegates_with_root_and_port(monkeypatch, tmp_path):
    seen = {}

    def _fake_serve(root, preferred_port, parent_pid=None):
        seen["root"] = root
        seen["port"] = preferred_port
        seen["parent_pid"] = parent_pid
        return 0

    monkeypatch.setattr(mcp_server, "_serve_streamable_http", _fake_serve)
    rc = mcp_server.main(["--root", str(tmp_path), "--transport", "streamable-http",
                          "--port", "9999", "--parent-pid", "777"])
    assert rc == 0
    assert seen == {"root": str(tmp_path.resolve()), "port": 9999, "parent_pid": 777}


def test_pick_loopback_port_returns_preferred_when_free():
    # Bind-and-release first to get a very-likely-free ephemeral port to use as "preferred".
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    assert mcp_server._pick_loopback_port(free_port) == free_port


def test_pick_loopback_port_resolves_the_real_port_when_preferred_is_zero():
    # preferred=0 means "any free port" — the OS always accepts a bind to port 0, so a
    # naive "bind succeeded -> return preferred" would wrongly hand back 0 itself.
    chosen = mcp_server._pick_loopback_port(0)
    assert chosen != 0
    assert 0 < chosen < 65536


def test_pick_loopback_port_falls_back_when_preferred_is_taken():
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        taken_port = holder.getsockname()[1]
        chosen = mcp_server._pick_loopback_port(taken_port)
        assert chosen != taken_port
        assert 0 < chosen < 65536
    finally:
        holder.close()


def test_serve_streamable_http_reuses_existing_instance_for_same_root(monkeypatch, tmp_path):
    monkeypatch.setattr("citevahti.paths.runtime_dir", lambda: tmp_path / "runtime")
    import os

    runtime_state.write_runtime_file(
        "mcp", url="http://127.0.0.1:8766", pid=os.getpid(), root="/proj",
        started_at="2026-07-01T00:00:00")

    def _boom(*a, **kw):
        raise AssertionError("build_server must not be called when reusing an existing instance")

    monkeypatch.setattr(mcp_server, "build_server", _boom)
    rc = mcp_server._serve_streamable_http("/proj", 8766)
    assert rc == 0


def test_serve_streamable_http_writes_and_clears_runtime_file(monkeypatch, tmp_path):
    monkeypatch.setattr("citevahti.paths.runtime_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr("citevahti.paths.log_dir", lambda: tmp_path / "Logs")

    class _FakeServer:
        def run(self, transport):
            # Confirm the runtime file exists while the "server" is up, before we
            # simulate it stopping (e.g. the user quitting the agent server).
            assert runtime_state.read_runtime_file("mcp") is not None
            raise KeyboardInterrupt

    monkeypatch.setattr(mcp_server, "build_server", lambda **kw: _FakeServer())
    with pytest.raises(KeyboardInterrupt):
        mcp_server._serve_streamable_http(str(tmp_path), 8766)
    assert runtime_state.read_runtime_file("mcp") is None
