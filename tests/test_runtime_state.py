"""``runtime_state.py`` — the sidecar handshake files under ``runtime/<name>.json``."""

from __future__ import annotations

import os

from citevahti import runtime_state


def _point_at(monkeypatch, tmp_path):
    monkeypatch.setattr("citevahti.paths.runtime_dir", lambda: tmp_path / "runtime")


def test_write_then_read_round_trips(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    runtime_state.write_runtime_file(
        "engine", url="http://127.0.0.1:8765", pid=os.getpid(), root="/proj",
        started_at="2026-07-01T00:00:00")
    data = runtime_state.read_runtime_file("engine")
    assert data == {
        "url": "http://127.0.0.1:8765", "pid": os.getpid(), "root": "/proj",
        "started_at": "2026-07-01T00:00:00",
    }


def test_read_missing_file_returns_none(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    assert runtime_state.read_runtime_file("mcp") is None


def test_stale_pid_is_treated_as_absent_and_file_is_removed(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    # A pid essentially guaranteed not to exist.
    dead_pid = 2**30
    runtime_state.write_runtime_file(
        "engine", url="http://127.0.0.1:8765", pid=dead_pid, root="/proj",
        started_at="2026-07-01T00:00:00")
    assert runtime_state.read_runtime_file("engine") is None
    assert not (tmp_path / "runtime" / "engine.json").exists()


def test_clear_runtime_file_is_idempotent(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    runtime_state.write_runtime_file(
        "mcp", url="http://127.0.0.1:8766", pid=os.getpid(), root="/proj",
        started_at="2026-07-01T00:00:00")
    runtime_state.clear_runtime_file("mcp")
    assert runtime_state.read_runtime_file("mcp") is None
    runtime_state.clear_runtime_file("mcp")  # calling again must not raise


def test_read_malformed_json_returns_none(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    d = tmp_path / "runtime"
    d.mkdir(parents=True)
    (d / "engine.json").write_text("not json", encoding="utf-8")
    assert runtime_state.read_runtime_file("engine") is None
