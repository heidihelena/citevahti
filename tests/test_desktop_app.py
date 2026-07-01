"""The CiteVahti.app shell: a pywebview window (never a browser) supervising two sidecars
(``citevahti-engine``, ``citevahti-mcp``). Fakes stand in for both the OS webview and the
sidecar supervisors — real subprocesses, real PyObjC menu bars, and real dialogs are out of
scope for headless unit tests (see the module docstring in ``desktop.py``); what's tested
here is the injectable orchestration: root resolution, start/stop ordering, first-run
consent, and app-state derivation.
"""

from __future__ import annotations

import os
import sys

import pytest

from citevahti import desktop, runtime_state
from citevahti.state import CiteVahtiStore
from citevahti.supervisor import SidecarSupervisor


def _isolate(monkeypatch, tmp_path):
    # Same isolation convention as tests/test_rootcfg.py — a fresh XDG_CONFIG_HOME/HOME so
    # these tests never touch the real machine's CiteVahti config/runtime files.
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdgcfg"))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CITEVAHTI_ROOT", raising=False)


class _NullLogger:
    def info(self, *a, **kw):
        pass

    def warning(self, *a, **kw):
        pass

    def exception(self, *a, **kw):
        pass


class _FakeSupervisor:
    """Stands in for ``SidecarSupervisor``: ``start()`` transitions synchronously to
    ``RUNNING`` (or ``ERROR``) and, when it "succeeds," writes the same runtime handshake
    file a real sidecar would — so ``CiteVahtiShell``'s reads of ``runtime_state`` behave
    exactly as they would against a real engine/mcp process."""

    def __init__(self, name, root, on_state_change=None, *, start_state=SidecarSupervisor.RUNNING,
                 url=None):
        self.name = name
        self.root = root
        self.on_state_change = on_state_change
        self.state = SidecarSupervisor.NOT_STARTED
        self.calls = []
        self._start_state = start_state
        self.url = url or f"http://127.0.0.1:0/{name}"

    def _transition(self, new_state):
        old, self.state = self.state, new_state
        if self.on_state_change:
            self.on_state_change(old, new_state)

    def start(self):
        self.calls.append("start")
        if self._start_state == SidecarSupervisor.RUNNING:
            runtime_state.write_runtime_file(
                self.name, url=self.url, pid=os.getpid(), root=self.root,
                started_at="2026-07-01T00:00:00")
        self._transition(self._start_state)

    def stop(self):
        self.calls.append("stop")
        runtime_state.clear_runtime_file(self.name)
        self._transition(SidecarSupervisor.STOPPED)

    def restart(self):
        self.calls.append("restart")
        self.start()


class _FakeWindow:
    def __init__(self, dialog_result=None):
        self.html_loaded = []
        self.urls_loaded = []
        self.dialog_result = dialog_result

    def load_html(self, html):
        self.html_loaded.append(html)

    def load_url(self, url):
        self.urls_loaded.append(url)

    def create_file_dialog(self, dialog_type):
        return self.dialog_result

    class _Events:
        def __iadd__(self, handler):
            return self

    events = _Events()


class _FakeWebview:
    FOLDER_DIALOG = "folder"

    def __init__(self, window=None):
        self.windows = []
        self.started = False
        self._window = window or _FakeWindow()

    def create_window(self, title, **kw):
        self.windows.append((title, kw))
        return self._window

    def start(self, func=None, **kw):
        self.started = True
        if func is not None:
            func()


def _make_shell(tmp_path, *, folder_picker=None, consent_prompt=None, order_log=None):
    calls = order_log if order_log is not None else []

    def _engine_factory(root, on_state_change=None):
        sup = _FakeSupervisor("engine", root, on_state_change)
        _wrap_for_order(sup, calls)
        return sup

    def _mcp_factory(root, on_state_change=None):
        sup = _FakeSupervisor("mcp", root, on_state_change)
        _wrap_for_order(sup, calls)
        return sup

    shell = desktop.CiteVahtiShell(
        webview=_FakeWebview(), engine_supervisor_factory=_engine_factory,
        mcp_supervisor_factory=_mcp_factory, folder_picker=folder_picker,
        consent_prompt=consent_prompt, logger=_NullLogger())
    shell.attach_window(_FakeWindow())
    return shell


def _wrap_for_order(sup, order_log):
    real_start, real_stop = sup.start, sup.stop

    def start():
        real_start()
        order_log.append((sup.name, "start"))

    def stop():
        real_stop()
        order_log.append((sup.name, "stop"))

    sup.start, sup.stop = start, stop


# ---- derive_app_state (pure) -------------------------------------------------
def test_derive_app_state_no_root_selected():
    assert desktop.derive_app_state("not_started", "not_started",
                                     root_selected=False, mcp_wanted=False) == desktop.NO_PROJECT


def test_derive_app_state_engine_starting():
    assert desktop.derive_app_state("starting", "not_started",
                                     root_selected=True, mcp_wanted=False) == desktop.STARTING_ENGINE


def test_derive_app_state_engine_error_wins_over_mcp():
    assert desktop.derive_app_state("error", "running",
                                     root_selected=True, mcp_wanted=True) == desktop.DEGRADED_PANEL_ERROR


def test_derive_app_state_panel_ready_when_mcp_not_wanted():
    assert desktop.derive_app_state("running", "not_started",
                                     root_selected=True, mcp_wanted=False) == desktop.PANEL_READY


def test_derive_app_state_starting_agent():
    assert desktop.derive_app_state("running", "starting",
                                     root_selected=True, mcp_wanted=True) == desktop.STARTING_AGENT


def test_derive_app_state_ready_when_both_running():
    assert desktop.derive_app_state("running", "running",
                                     root_selected=True, mcp_wanted=True) == desktop.READY


def test_derive_app_state_degraded_agent_error():
    assert desktop.derive_app_state("running", "error",
                                     root_selected=True, mcp_wanted=True) == desktop.DEGRADED_AGENT_ERROR


def test_derive_app_state_stopping():
    assert desktop.derive_app_state("stopping", "running",
                                     root_selected=True, mcp_wanted=True) == desktop.STOPPING


# ---- boot flow: folder resolution ---------------------------------------------
def test_boot_starts_engine_and_loads_panel_when_root_already_has_a_ledger(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    shell = _make_shell(tmp_path, consent_prompt=lambda: False)

    shell.on_started()

    assert shell.root == str(project.resolve())
    assert shell.engine.state == SidecarSupervisor.RUNNING
    assert shell._window.urls_loaded == ["http://127.0.0.1:0/engine"]
    assert shell._window.html_loaded == []   # never fell back to an error/no-project screen


def test_boot_prompts_for_a_folder_when_nothing_resolvable(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)   # no ledger here, and none remembered yet
    chosen = tmp_path / "chosen"
    shell = _make_shell(tmp_path, folder_picker=lambda: str(chosen), consent_prompt=lambda: False)

    shell.on_started()

    assert shell.root == str(chosen.resolve())
    assert CiteVahtiStore(chosen).exists()          # store initialized for the new folder
    assert shell.engine.state == SidecarSupervisor.RUNNING


def test_boot_cancelled_folder_picker_does_not_start_engine(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    shell = _make_shell(tmp_path, folder_picker=lambda: None)

    shell.on_started()

    assert shell.engine is None
    assert shell.root is None
    assert any("No project folder selected" in h for h in shell._window.html_loaded)
    assert shell.app_state == desktop.NO_PROJECT


# ---- first-run MCP consent -----------------------------------------------------
def test_first_run_consent_enable_starts_mcp_after_engine(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    order = []
    shell = _make_shell(tmp_path, consent_prompt=lambda: True, order_log=order)

    shell.on_started()

    assert order == [("engine", "start"), ("mcp", "start")]   # engine first, then mcp
    from citevahti import appprefs
    assert appprefs.get_mcp_autostart() is True


def test_first_run_consent_decline_does_not_start_mcp_and_persists(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    shell = _make_shell(tmp_path, consent_prompt=lambda: False)

    shell.on_started()

    assert shell.mcp is None
    from citevahti import appprefs
    assert appprefs.get_mcp_autostart() is False


def test_prior_autostart_true_skips_the_prompt(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    from citevahti import appprefs
    appprefs.set_mcp_autostart(True)

    def _boom():
        raise AssertionError("must not prompt when a choice is already persisted")

    shell = _make_shell(tmp_path, consent_prompt=_boom)
    shell.on_started()
    assert shell.mcp is not None and shell.mcp.state == SidecarSupervisor.RUNNING


# ---- Copy MCP Connection Info gating -------------------------------------------
def test_copy_mcp_connection_info_disabled_before_running_enabled_after(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    shell = _make_shell(tmp_path, consent_prompt=lambda: False)
    shell.on_started()
    assert shell.mcp_connection_url() is None
    assert shell.copy_mcp_connection_info() is False

    shell._start_mcp()
    assert shell.mcp.state == SidecarSupervisor.RUNNING
    assert shell.mcp_connection_url() == "http://127.0.0.1:0/mcp"
    assert shell.copy_mcp_connection_info() is True


# ---- choose project folder: stop order, then restart against the new root ------
def test_choose_project_folder_stops_mcp_then_engine_before_switching(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    order = []
    shell = _make_shell(tmp_path, consent_prompt=lambda: True, order_log=order)
    shell.on_started()
    order.clear()

    new_folder = tmp_path / "new-project"
    shell.folder_picker = lambda: str(new_folder)
    shell.choose_project_folder()

    assert order == [
        ("mcp", "stop"), ("engine", "stop"), ("engine", "start"), ("mcp", "start"),
    ]
    assert shell.root == str(new_folder.resolve())
    assert CiteVahtiStore(new_folder).exists()


def test_choose_project_folder_cancelled_leaves_current_project_untouched(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    shell = _make_shell(tmp_path, consent_prompt=lambda: False)
    shell.on_started()
    original_root = shell.root

    shell.folder_picker = lambda: None
    shell.choose_project_folder()

    assert shell.root == original_root
    assert shell.engine.calls.count("stop") == 0


# ---- quit: idempotent, MCP before engine ---------------------------------------
def test_quit_stops_mcp_before_engine_and_is_idempotent(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    order = []
    shell = _make_shell(tmp_path, consent_prompt=lambda: True, order_log=order)
    shell.on_started()
    order.clear()

    shell.quit()
    assert order == [("mcp", "stop"), ("engine", "stop")]

    order.clear()
    shell.quit()   # idempotent — no further calls
    assert order == []


# ---- run_app() wiring ----------------------------------------------------------
def test_run_app_creates_a_window_with_the_starting_screen_then_boots(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)

    def _engine_factory(root, on_state_change=None):
        return _FakeSupervisor("engine", root, on_state_change)

    fake_webview = _FakeWebview()
    rc = desktop.run_app(webview=fake_webview, engine_supervisor_factory=_engine_factory,
                         consent_prompt=lambda: False)

    assert rc == 0
    assert fake_webview.started
    assert len(fake_webview.windows) == 1
    title, kw = fake_webview.windows[0]
    assert "CiteVahti" in title
    assert "Starting" in kw.get("html", "")
    assert kw.get("width") and kw.get("min_size")
    # the fake start() ran func() synchronously, so boot already completed:
    assert fake_webview._window.urls_loaded == ["http://127.0.0.1:0/engine"]


def test_missing_pywebview_gives_an_install_hint(monkeypatch):
    # Exercise the error path regardless of whether the [app] extra is installed: a None
    # entry in sys.modules makes `import webview` raise ImportError, simulating its absence.
    monkeypatch.setitem(sys.modules, "webview", None)
    with pytest.raises(RuntimeError, match=r"citevahti\[app\]"):
        desktop._import_webview()
