"""``engine.py`` — the ``citevahti-engine`` sidecar entry point.

``launch_panel`` itself is already tested (``tests/test_start.py``); here we only check the
engine's own responsibilities: loopback-only enforcement, writing/clearing the runtime
handshake file, and a clean shutdown on ``SIGTERM``.
"""

from __future__ import annotations

import os
import signal
import threading
import time

from citevahti import engine, runtime_state


class FakeHttpd:
    def __init__(self):
        self.shutdown_called = False
        self.server_close_called = False

    def shutdown(self):
        self.shutdown_called = True

    def server_close(self):
        self.server_close_called = True


def _restore_signals():
    original = {
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        signal.SIGINT: signal.getsignal(signal.SIGINT),
    }

    def _restore():
        for sig, handler in original.items():
            signal.signal(sig, handler)

    return _restore


def test_main_writes_runtime_file_and_shuts_down_cleanly_on_sigterm(tmp_path, monkeypatch):
    monkeypatch.setattr("citevahti.paths.runtime_dir", lambda: tmp_path / "runtime")
    fake_httpd = FakeHttpd()
    monkeypatch.setattr(engine, "launch_panel", lambda root, **kw: {
        "status": "started", "url": "http://127.0.0.1:8765", "browser_opened": False,
        "_httpd": fake_httpd,
    })
    restore = _restore_signals()
    try:
        def _send_sigterm_soon():
            time.sleep(0.2)
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=_send_sigterm_soon, daemon=True).start()
        rc = engine.main(["--root", str(tmp_path)])
    finally:
        restore()

    assert rc == 0
    assert fake_httpd.shutdown_called
    assert fake_httpd.server_close_called
    assert runtime_state.read_runtime_file("engine") is None


def test_main_refuses_non_loopback_result(monkeypatch, tmp_path):
    monkeypatch.setattr("citevahti.paths.runtime_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(engine, "launch_panel", lambda root, **kw: {
        "status": "refused_non_loopback", "url": None, "browser_opened": False, "_httpd": None,
    })
    rc = engine.main(["--root", str(tmp_path)])
    assert rc == 2
    assert runtime_state.read_runtime_file("engine") is None


def test_main_returns_2_on_port_conflict_without_writing_runtime_file(monkeypatch, tmp_path):
    monkeypatch.setattr("citevahti.paths.runtime_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(engine, "launch_panel", lambda root, **kw: {
        "status": "port_conflict", "url": "http://127.0.0.1:8765", "browser_opened": False,
        "_httpd": None,
    })
    rc = engine.main(["--root", str(tmp_path)])
    assert rc == 2
    assert runtime_state.read_runtime_file("engine") is None
