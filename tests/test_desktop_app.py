"""The native desktop window (`citevahti-app`): it shows the existing loopback panel in
an OS webview — not a browser — reusing the panel server unchanged. The GUI itself needs
a display, so these tests inject a fake webview and assert the wiring: a loopback URL, a
window (never a browser), and a clear error when pywebview isn't installed."""

from __future__ import annotations

import sys

import pytest

from citevahti import desktop
from citevahti.state import CiteVahtiStore


class _FakeWebview:
    def __init__(self):
        self.windows = []
        self.started = False

    def create_window(self, title, url, **kw):
        self.windows.append((title, url, kw))

    def start(self, **kw):
        self.started = True


def test_run_app_shows_the_loopback_panel_in_a_native_window(tmp_path):
    CiteVahtiStore(tmp_path).init()
    fake = _FakeWebview()
    rc = desktop.run_app(str(tmp_path), port=0, webview=fake)
    assert rc == 0
    assert fake.started                                   # the native window opened
    assert len(fake.windows) == 1
    title, url, kw = fake.windows[0]
    assert "CiteVahti" in title
    assert url.startswith("http://127.0.0.1:")            # the loopback panel, in-window
    assert kw.get("width") and kw.get("min_size")         # a real sized app window


def test_run_app_never_opens_a_browser(tmp_path, monkeypatch):
    # the whole point is "desktop, not chrome" — launch_panel must be told open_browser=False
    CiteVahtiStore(tmp_path).init()
    seen = {}
    real = desktop.launch_panel

    def spy(root, **kw):
        seen.update(kw)
        return real(root, **kw)

    monkeypatch.setattr(desktop, "launch_panel", spy)
    desktop.run_app(str(tmp_path), port=0, webview=_FakeWebview())
    assert seen.get("open_browser") is False


def test_missing_pywebview_gives_an_install_hint(monkeypatch):
    # Exercise the error path regardless of whether the [app] extra is installed: a None
    # entry in sys.modules makes `import webview` raise ImportError, simulating its absence.
    # (Previously this skipped whenever pywebview was present — i.e. always, in CI.)
    monkeypatch.setitem(sys.modules, "webview", None)
    with pytest.raises(RuntimeError, match=r"citevahti\[app\]"):
        desktop._import_webview()
