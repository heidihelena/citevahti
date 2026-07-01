"""``appprefs.py`` — tri-state ``mcp_autostart`` persisted at ``~/.config/citevahti/app.json``."""

from __future__ import annotations

from citevahti import appprefs


def _point_at(monkeypatch, tmp_path):
    monkeypatch.setattr("citevahti.paths.config_dir", lambda: tmp_path / "citevahti")


def test_get_mcp_autostart_unset_by_default(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    assert appprefs.get_mcp_autostart() is None


def test_set_then_get_round_trips_true(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    appprefs.set_mcp_autostart(True)
    assert appprefs.get_mcp_autostart() is True


def test_set_then_get_round_trips_false(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    appprefs.set_mcp_autostart(False)
    assert appprefs.get_mcp_autostart() is False


def test_load_app_prefs_missing_file_is_empty_dict(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    assert appprefs.load_app_prefs() == {}


def test_save_app_prefs_never_raises_on_bad_path(monkeypatch):
    from pathlib import Path

    # "/dev/null" is a file, not a directory — mkdir(parents=True) under it must OSError.
    monkeypatch.setattr("citevahti.paths.config_dir", lambda: Path("/dev/null/not-a-real-dir"))
    appprefs.save_app_prefs({"mcp_autostart": True})  # must not raise


def test_env_override_true(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    appprefs.set_mcp_autostart(False)
    monkeypatch.setenv("CITEVAHTI_MCP_AUTOSTART", "1")
    assert appprefs.get_mcp_autostart() is True


def test_env_override_false(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    appprefs.set_mcp_autostart(True)
    monkeypatch.setenv("CITEVAHTI_MCP_AUTOSTART", "0")
    assert appprefs.get_mcp_autostart() is False


def test_env_override_absent_falls_back_to_persisted(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    appprefs.set_mcp_autostart(True)
    monkeypatch.delenv("CITEVAHTI_MCP_AUTOSTART", raising=False)
    assert appprefs.get_mcp_autostart() is True
