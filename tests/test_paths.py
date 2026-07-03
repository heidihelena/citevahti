"""``paths.py`` — where the desktop app writes logs/config and finds its sidecar binaries."""

from __future__ import annotations

import sys

import pytest

from citevahti import paths

# Captured at import time, before any fixture runs: this module asserts the REAL
# platform resolution that conftest's autouse ``_isolate_host_state`` deliberately
# replaces for every other test. These tests only build path strings under fake
# HOME/XDG env vars — they never create or write the directories.
_REAL_LOG_DIR = paths.log_dir
_REAL_RUNTIME_DIR = paths.runtime_dir


@pytest.fixture(autouse=True)
def _real_path_resolution(monkeypatch):
    monkeypatch.setattr("citevahti.paths.log_dir", _REAL_LOG_DIR)
    monkeypatch.setattr("citevahti.paths.runtime_dir", _REAL_RUNTIME_DIR)


def test_log_dir_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    d = paths.log_dir()
    assert str(d).endswith("Library/Logs/CiteVahti")


def test_log_dir_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "/fake/AppData/Local")
    d = paths.log_dir()
    assert str(d) == "/fake/AppData/Local/CiteVahti/Logs"


def test_log_dir_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", "/fake/state")
    d = paths.log_dir()
    assert str(d) == "/fake/state/citevahti/log"


def test_config_dir_honours_xdg_config_home(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/fake/config")
    assert str(paths.config_dir()) == "/fake/config/citevahti"


def test_runtime_dir_is_under_config_dir(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/fake/config")
    assert str(paths.runtime_dir()) == "/fake/config/citevahti/runtime"


def test_bundled_binary_none_when_not_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.bundled_binary("citevahti-engine") is None


def test_bundled_binary_prefers_the_onedir_layout(monkeypatch, tmp_path):
    # Contents/MacOS/citevahti-engine/citevahti-engine — the real, shipped layout (chosen
    # over --onefile because it avoids a per-launch Gatekeeper re-scan, see the docstring).
    nested = tmp_path / "citevahti-engine"
    nested.mkdir()
    exe = nested / "citevahti-engine"
    exe.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "CiteVahti"))
    assert paths.bundled_binary("citevahti-engine") == exe


def test_bundled_binary_falls_back_to_the_flat_onefile_layout(monkeypatch, tmp_path):
    sibling = tmp_path / "citevahti-engine"
    sibling.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "CiteVahti"))
    assert paths.bundled_binary("citevahti-engine") == sibling


def test_bundled_binary_none_when_sibling_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "CiteVahti"))
    assert paths.bundled_binary("citevahti-mcp") is None


def test_dev_fallback_cmd_uses_current_interpreter():
    cmd = paths.dev_fallback_cmd("citevahti.engine")
    assert cmd == [sys.executable, "-m", "citevahti.engine"]
