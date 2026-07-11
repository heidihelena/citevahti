"""The CiteVahti.app shell: a pywebview window (never a browser) supervising two sidecars
(``citevahti-engine``, ``citevahti-mcp``). Fakes stand in for both the OS webview and the
sidecar supervisors — real subprocesses, real PyObjC menu bars, and real dialogs are out of
scope for headless unit tests (see the module docstring in ``desktop.py``); what's tested
here is the injectable orchestration: root resolution, start/stop ordering, the
moment-of-intent agent-server consent gate, window re-heal on engine restart/error, and
app-state derivation.
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


# ---- MCP consent: at the moment of intent, never at first launch ----------------
def test_boot_never_prompts_and_never_starts_mcp_when_pref_unset(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)

    def _boom():
        raise AssertionError("boot must never show the consent prompt")

    shell = _make_shell(tmp_path, consent_prompt=_boom)
    shell.on_started()

    assert shell.mcp is None
    from citevahti import appprefs
    assert appprefs.get_mcp_autostart() is None   # untouched — no choice was made


def test_start_agent_server_asks_consent_then_starts_and_persists(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    order = []
    prompts = []

    def _consent():
        prompts.append(True)
        return True

    shell = _make_shell(tmp_path, consent_prompt=_consent, order_log=order)
    shell.on_started()
    shell.toggle_mcp()   # the user's "Start Agent Server" click

    assert prompts == [True]   # asked exactly once, at the click
    assert order == [("engine", "start"), ("mcp", "start")]   # engine first, then mcp
    from citevahti import appprefs
    assert appprefs.get_mcp_autostart() is True


def test_consent_decline_persists_nothing_and_asks_again_next_time(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    prompts = []

    def _decline():
        prompts.append(False)
        return False

    shell = _make_shell(tmp_path, consent_prompt=_decline)
    shell.on_started()

    shell.toggle_mcp()   # "Not Now"
    assert shell.mcp is None
    from citevahti import appprefs
    assert appprefs.get_mcp_autostart() is None   # "Not Now" genuinely means not now

    shell.toggle_mcp()   # a later click asks again rather than staying silently declined
    assert prompts == [False, False]


def test_prior_autostart_true_starts_mcp_at_boot_without_a_prompt(tmp_path, monkeypatch):
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


def test_reenable_after_stop_does_not_reprompt(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    prompts = []

    def _consent():
        prompts.append(True)
        return True

    shell = _make_shell(tmp_path, consent_prompt=_consent)
    shell.on_started()
    shell.toggle_mcp()   # enable (consents)
    shell.toggle_mcp()   # stop
    shell.toggle_mcp()   # re-enable — consent was already given once
    assert prompts == [True]
    assert shell.mcp.state == SidecarSupervisor.RUNNING


def test_restart_mcp_without_a_session_routes_through_the_consent_gate(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    shell = _make_shell(tmp_path, consent_prompt=lambda: False)
    shell.on_started()

    shell.restart_mcp()   # never started this session, never consented -> gate applies
    assert shell.mcp is None


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
    shell.toggle_mcp()   # user enables the agent server (consents at the click)
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


# ---- window re-heal: the window must track the engine, not just the menu bar ----
def test_engine_restart_reloads_the_panel_into_the_window(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    shell = _make_shell(tmp_path, consent_prompt=lambda: False)
    shell.on_started()
    assert shell._window.urls_loaded == ["http://127.0.0.1:0/engine"]

    # A crash + supervised restart: the page loaded before the crash points at a dead
    # port/CSRF session, so the RUNNING transition must push a fresh load.
    shell.engine._transition(SidecarSupervisor.STARTING)
    shell.engine._transition(SidecarSupervisor.RUNNING)
    assert shell._window.urls_loaded == ["http://127.0.0.1:0/engine"] * 2


def test_engine_error_mid_session_takes_over_the_window(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    shell = _make_shell(tmp_path, consent_prompt=lambda: False)
    shell.on_started()
    assert shell._window.html_loaded == []

    shell.engine._transition(SidecarSupervisor.ERROR)
    assert any("trouble starting" in h for h in shell._window.html_loaded)


def test_boot_does_not_double_load_the_panel(tmp_path, monkeypatch):
    # The boot-time RUNNING transition happens before the first _load_panel_url, so the
    # re-heal hook must stay quiet then — exactly one load at startup.
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    shell = _make_shell(tmp_path, consent_prompt=lambda: False)
    shell.on_started()
    assert shell._window.urls_loaded == ["http://127.0.0.1:0/engine"]


# ---- sidecar commands carry the parent-death watchdog flag ----------------------
def test_sidecar_commands_pass_our_pid_for_the_parent_watchdog():
    engine_cmd = desktop._engine_cmd("/some/root")
    mcp_cmd = desktop._mcp_cmd("/some/root")
    for cmd in (engine_cmd, mcp_cmd):
        assert "--parent-pid" in cmd
        assert cmd[cmd.index("--parent-pid") + 1] == str(os.getpid())


# ---- quit: idempotent, MCP before engine ---------------------------------------
def test_quit_stops_mcp_before_engine_and_is_idempotent(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    order = []
    shell = _make_shell(tmp_path, consent_prompt=lambda: True, order_log=order)
    shell.on_started()
    shell.toggle_mcp()   # user enables the agent server (consents at the click)
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


# ---- sidecar liveness probing: cheap, tolerant, never /api/health ----------------
def test_engine_probe_pings_the_cheap_endpoint_with_a_tolerant_timeout(tmp_path, monkeypatch):
    """The probe must hit /api/ping (constant-time), never /api/health (live Zotero/
    PubMed checks, routinely >1 s) — and give a loaded machine room to answer. The
    old health-on-1s probe declared a healthy engine wedged 3× in a minute
    (2026-07-02), and every kill stranded the panel window."""
    _isolate(monkeypatch, tmp_path)
    runtime_state.write_runtime_file(
        "engine", url="http://127.0.0.1:65432", pid=os.getpid(), root=str(tmp_path),
        started_at="2026-07-02T00:00:00")
    calls = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    def fake_get(url, timeout):
        calls["url"], calls["timeout"] = url, timeout
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)
    probe = desktop._engine_health_probe(str(tmp_path))
    assert probe() is True
    assert calls["url"].endswith("/api/ping"), "liveness must never probe the expensive /api/health"
    assert calls["timeout"] >= 3.0


def test_engine_probe_fails_closed_on_connection_error_and_foreign_root(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    probe = desktop._engine_health_probe(str(tmp_path))
    assert probe() is False                      # no runtime file yet

    runtime_state.write_runtime_file(
        "engine", url="http://127.0.0.1:65432", pid=os.getpid(), root="/somewhere/else",
        started_at="2026-07-02T00:00:00")
    assert probe() is False                      # another project's engine is not our health

    runtime_state.write_runtime_file(
        "engine", url="http://127.0.0.1:65432", pid=os.getpid(), root=str(tmp_path),
        started_at="2026-07-02T00:00:00")

    import httpx

    def refuse(url, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(httpx, "get", refuse)
    assert probe() is False


def test_sidecar_supervisors_tolerate_transient_probe_misses(tmp_path, monkeypatch):
    """wedge_threshold=3 at ~1 s polls killed a HEALTHY engine on a busy machine; the
    shell must configure a tolerance momentary load can survive. A genuinely wedged
    sidecar is still wedged ten seconds later."""
    _isolate(monkeypatch, tmp_path)
    assert desktop._default_engine_supervisor(str(tmp_path)).wedge_threshold >= 10
    assert desktop._default_mcp_supervisor(str(tmp_path)).wedge_threshold >= 10


# ---- close = hide, never quit (pilot finding 2026-07-11) ------------------------
class _HidableWindow(_FakeWindow):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.hidden = 0
        self.shown = 0

    def hide(self):
        self.hidden += 1

    def show(self):
        self.shown += 1


def test_closing_the_window_hides_it_and_never_stops_the_sidecars(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    order = []
    shell = _make_shell(tmp_path, order_log=order)
    window = _HidableWindow()
    shell.attach_window(window)
    shell.on_started()
    order.clear()

    handler = desktop.make_close_handler(shell, window)
    assert handler() is False              # close is cancelled…
    assert window.hidden == 1              # …the window is hidden instead
    assert order == []                     # and NO sidecar was stopped
    assert not shell._quit_started


def test_close_is_allowed_through_while_quitting(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    shell = _make_shell(tmp_path)
    window = _HidableWindow()
    shell.attach_window(window)
    shell.on_started()
    shell.quit()

    handler = desktop.make_close_handler(shell, window)
    assert handler() is True               # a real quit must never be blocked
    assert window.hidden == 0


def test_close_falls_back_to_closing_when_hide_is_unavailable(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    shell = _make_shell(tmp_path)
    window = _FakeWindow()                 # no hide() at all → AttributeError inside
    handler = desktop.make_close_handler(shell, window)
    assert handler() is True               # degrade to the old behaviour, don't wedge


def test_open_panel_shows_the_hidden_window_and_reloads_only_when_needed(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    CiteVahtiStore(project).init()
    monkeypatch.chdir(project)
    shell = _make_shell(tmp_path)
    window = _HidableWindow()
    shell.attach_window(window)
    shell.on_started()                     # boots + loads the panel once
    loads_after_boot = len(window.urls_loaded)

    shell.open_panel()                     # panel already showing → show, no reload
    assert window.shown == 1
    assert len(window.urls_loaded) == loads_after_boot

    shell._show_engine_error()             # window no longer shows the panel…
    shell.open_panel()                     # …so opening must reload it
    assert window.shown == 2
    assert len(window.urls_loaded) == loads_after_boot + 1
