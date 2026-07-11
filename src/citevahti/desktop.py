"""The CiteVahti.app shell: Dock icon, menu-bar icon, the pywebview window, the project
folder picker, and two supervised sidecars — never a browser tab, never a Terminal window.

``citevahti-app`` opens a pywebview window immediately (a "Starting CiteVahti…" screen),
then — once the native GUI loop is live — resolves or asks for a project folder, starts
the ``citevahti-engine`` sidecar (the review panel + project store, see ``engine.py``),
waits for it to report healthy, and loads its panel URL into the window. If the user has
enabled it, it also starts the ``citevahti-mcp`` sidecar in ``streamable-http`` mode (the
agent-facing interface — see ``agent/mcp_server.py``) so a chat client can help screen
citations, without ever bypassing the human-rates-first boundary already enforced by
``agent/policy.py``. Enabling is opt-in **at the moment of intent**: the consent dialog
appears the first time the user chooses "Start Agent Server", never as a first-launch
prompt — a question asked before the product means anything can't be answered informedly,
and declining ("Not Now") persists nothing, so it genuinely means *not now*.

Both sidecars are supervised by a :class:`~citevahti.supervisor.SidecarSupervisor` (crash
detection, restart with backoff, clean stop) rather than run as background threads inside
this process — a thread can't be killed or restarted independently the way a subprocess
can, which is the whole reason this file no longer calls ``launch_panel`` directly.

The PyObjC/AppKit pieces (menu-bar item, quit notification observer, consent alert) are
best-effort, guarded, macOS-only shims with no meaningful headless test coverage — there is
no Cocoa run loop in CI. AppKit is main-thread-only, and pywebview runs the ``start()``
callback on a background thread, so every AppKit touch here goes through
:func:`_dispatch_on_main` (or arrives on the main thread already, as menu actions do).
They're kept deliberately thin; the logic worth testing (root resolution, start/stop
ordering, app-state derivation) lives in plain, injectable methods on
:class:`CiteVahtiShell` instead. Manual verification is via the ``run``/``verify`` skill
against a built ``.app``.
"""

from __future__ import annotations

import atexit
import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from . import appprefs, applog, paths, runtime_state
from .rootcfg import has_ledger, remember_root, resolve_root
from .state import CiteVahtiStore
from .supervisor import SidecarSupervisor

_TITLE = "CiteVahti — manuscript citation review"

_STARTING_HTML = """<!doctype html><html><body style="font:15px -apple-system,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;color:#444">
<p>Starting CiteVahti&hellip;</p></body></html>"""

_NO_PROJECT_HTML = """<!doctype html><html><body style="font:15px -apple-system,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;color:#444">
<p>No project folder selected.<br>Choose one from the CiteVahti menu-bar icon.</p>
</body></html>"""

_ENGINE_ERROR_HTML = """<!doctype html><html><body style="font:15px -apple-system,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;color:#444">
<p>CiteVahti had trouble starting.<br>Try "Restart Panel Engine" from the menu bar.</p>
</body></html>"""

# ---- app-level derived state (drives the menu-bar status rows) --------------
NO_PROJECT = "no_project"
STARTING_ENGINE = "starting_engine"
PANEL_READY = "panel_ready"
STARTING_AGENT = "starting_agent"
READY = "ready"
DEGRADED_PANEL_ERROR = "degraded_panel_error"
DEGRADED_AGENT_ERROR = "degraded_agent_error"
STOPPING = "stopping"


def derive_app_state(engine_state: str, mcp_state: str, *, root_selected: bool,
                      mcp_wanted: bool) -> str:
    """A pure function from both sidecars' states (+ whether a project/AI-agent is
    wanted) to one app-level state — keeps the menu-bar UI from growing into ad-hoc
    if/else spaghetti across two independent state machines."""
    if not root_selected:
        return NO_PROJECT
    if engine_state == SidecarSupervisor.STOPPING or mcp_state == SidecarSupervisor.STOPPING:
        return STOPPING
    if engine_state == SidecarSupervisor.ERROR:
        return DEGRADED_PANEL_ERROR
    if engine_state != SidecarSupervisor.RUNNING:
        return STARTING_ENGINE
    if not mcp_wanted:
        return PANEL_READY
    if mcp_state == SidecarSupervisor.ERROR:
        return DEGRADED_AGENT_ERROR
    if mcp_state == SidecarSupervisor.RUNNING:
        return READY
    if mcp_state == SidecarSupervisor.STARTING:
        return STARTING_AGENT
    return PANEL_READY   # mcp not started yet / stopped and not currently wanted


# ---- sidecar command + health-probe builders --------------------------------
# Both sidecars get --parent-pid so they exit on their own if this shell dies without
# running quit() (Force Quit, a GUI-layer crash) — see parentwatch.py. Without it, an
# invisible engine/agent server outlives the app the user believes controls it.
def _engine_cmd(root: str) -> list[str]:
    tail = ["--root", root, "--parent-pid", str(os.getpid())]
    binary = paths.bundled_binary("citevahti-engine")
    if binary is not None:
        return [str(binary)] + tail
    return paths.dev_fallback_cmd("citevahti.engine") + tail


def _mcp_cmd(root: str) -> list[str]:
    tail = ["--root", root, "--transport", "streamable-http",
            "--parent-pid", str(os.getpid())]
    binary = paths.bundled_binary("citevahti-mcp")
    if binary is not None:
        return [str(binary)] + tail
    return paths.dev_fallback_cmd("citevahti.agent.mcp_server") + tail


# Liveness probing must be cheap and tolerant. /api/health is NOT a liveness endpoint —
# its live Zotero/PubMed connection checks routinely take >1 s, and probing it on a 1 s
# timeout declared a healthy engine "wedged" three times in a minute on a busy machine
# (2026-07-02), killing it and stranding the panel window each time. Probe the constant-
# time /api/ping instead, with a timeout sized for a loaded machine, not a fast one.
_PROBE_TIMEOUT = 3.0


def _engine_health_probe(root: str) -> Callable[[], bool]:
    def probe() -> bool:
        data = runtime_state.read_runtime_file("engine")
        if data is None or data.get("root") != root:
            return False
        try:
            import httpx
            resp = httpx.get(f"{data['url']}/api/ping", timeout=_PROBE_TIMEOUT)
        except Exception:
            return False
        return resp.status_code == 200 and resp.json().get("ok") is True
    return probe


def _mcp_health_probe(root: str) -> Callable[[], bool]:
    def probe() -> bool:
        data = runtime_state.read_runtime_file("mcp")
        if data is None or data.get("root") != root:
            return False
        try:
            import httpx
            resp = httpx.get(f"{data['url']}/health", timeout=_PROBE_TIMEOUT)
            body = resp.json()
        except Exception:
            return False
        return (resp.status_code == 200 and body.get("ok") is True
                and body.get("root") == root)
    return probe


# A generous startup allowance for the frozen sidecar binaries: on a slower machine or a
# cold disk cache, a freshly-launched --onedir executable can still take longer than
# SidecarSupervisor's bare 10s default (measured ~1-12s on a fast Apple Silicon Mac after
# switching off --onefile — see build-app.sh — but that's one machine, not a guarantee).
_SIDECAR_STARTUP_TIMEOUT = 30.0


# How many consecutive failed probes (at ~1 s intervals) before a sidecar is declared
# wedged and restarted. The default 3 proved trigger-happy: three slow seconds on a busy
# machine murdered a perfectly healthy engine (2026-07-02). A genuinely wedged sidecar is
# still wedged ten seconds later; a machine under momentary load is not.
_SIDECAR_WEDGE_THRESHOLD = 10


def _default_engine_supervisor(root: str, on_state_change=None) -> SidecarSupervisor:
    return SidecarSupervisor(
        "engine", _engine_cmd(root), _engine_health_probe(root),
        on_state_change=on_state_change, logger=applog.get_logger("app"),
        runtime_name="engine", startup_timeout=_SIDECAR_STARTUP_TIMEOUT,
        wedge_threshold=_SIDECAR_WEDGE_THRESHOLD)


def _default_mcp_supervisor(root: str, on_state_change=None) -> SidecarSupervisor:
    return SidecarSupervisor(
        "mcp", _mcp_cmd(root), _mcp_health_probe(root),
        on_state_change=on_state_change, logger=applog.get_logger("app"),
        runtime_name="mcp", startup_timeout=_SIDECAR_STARTUP_TIMEOUT,
        wedge_threshold=_SIDECAR_WEDGE_THRESHOLD)


# ---- the shell ---------------------------------------------------------------
class CiteVahtiShell:
    """Owns the two sidecar supervisors, the project root, and the pywebview window's
    content. Every OS-integration point (dialogs, menu bar, quit) is either injected (for
    tests) or guarded PyObjC (for production) — this class itself has no Cocoa import."""

    def __init__(self, *, webview=None,
                 engine_supervisor_factory=_default_engine_supervisor,
                 mcp_supervisor_factory=_default_mcp_supervisor,
                 folder_picker: Optional[Callable[[], Optional[str]]] = None,
                 consent_prompt: Optional[Callable[[], bool]] = None,
                 logger=None) -> None:
        self.webview = webview
        self._engine_supervisor_factory = engine_supervisor_factory
        self._mcp_supervisor_factory = mcp_supervisor_factory
        self.folder_picker = folder_picker
        self.consent_prompt = consent_prompt
        self.logger = logger or applog.get_logger("app")
        self.root: Optional[str] = None
        self.engine: Optional[SidecarSupervisor] = None
        self.mcp: Optional[SidecarSupervisor] = None
        self._window = None
        self._panel_loaded = False
        self._quit_started = False
        self._quit_observer: object = None   # keeps a strong ref to the PyObjC observer alive
        self.on_state_refresh: Callable[[], None] = lambda: None   # menu-bar hook

    def attach_window(self, window) -> None:
        self._window = window

    # ---- app-level status --------------------------------------------------
    @property
    def app_state(self) -> str:
        engine_state = self.engine.state if self.engine else SidecarSupervisor.NOT_STARTED
        mcp_state = self.mcp.state if self.mcp else SidecarSupervisor.NOT_STARTED
        return derive_app_state(
            engine_state, mcp_state, root_selected=self.root is not None,
            mcp_wanted=bool(appprefs.get_mcp_autostart()))

    def mcp_connection_url(self) -> Optional[str]:
        data = runtime_state.read_runtime_file("mcp")
        return data.get("url") if data else None

    # ---- boot flow (called once the GUI loop is live) -----------------------
    def on_started(self) -> None:
        try:
            self._boot()
        except Exception:
            self.logger.exception("failed during startup")

    def _boot(self) -> None:
        candidate = resolve_root(None)
        if not has_ledger(candidate):
            chosen = self._pick_folder()
            if not chosen:
                self.logger.info("no project folder selected")
                self._show_no_project()
                return
            candidate = chosen
        self._activate_root(candidate)
        if not self._wait_for_engine_running():
            self._show_engine_error()
            return
        self._load_panel_url()
        if appprefs.get_mcp_autostart():
            self._start_mcp()   # a previously-enabled agent server comes back on its own

    def _pick_folder(self) -> Optional[str]:
        if self.folder_picker is not None:
            return self.folder_picker()
        if self.webview is None or self._window is None:
            return None
        try:
            result = self._window.create_file_dialog(self.webview.FOLDER_DIALOG)
        except Exception:
            return None
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    def _activate_root(self, folder: str) -> None:
        folder = str(Path(folder).expanduser().resolve())
        remember_root(folder)
        store = CiteVahtiStore(folder)
        if not store.exists():
            store.init()
        self.root = folder
        self.engine = self._engine_supervisor_factory(folder, self._on_engine_state_change)
        self.engine.start()

    def _wait_for_engine_running(self, timeout: float = _SIDECAR_STARTUP_TIMEOUT + 5.0) -> bool:
        if self.engine is None:   # only called right after _activate_root() sets it
            raise RuntimeError("_wait_for_engine_running called before an engine was started")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.engine.state == SidecarSupervisor.RUNNING:
                return True
            if self.engine.state == SidecarSupervisor.ERROR:
                return False
            time.sleep(0.05)
        return False

    def _ask_mcp_consent(self) -> bool:
        if self.consent_prompt is not None:
            return self.consent_prompt()
        return _native_consent_dialog()

    # ---- sidecar start/stop --------------------------------------------------
    def _start_mcp(self) -> None:
        if self.root is None:
            return
        self.mcp = self._mcp_supervisor_factory(self.root, self._on_any_state_change)
        self.mcp.start()

    def _stop_mcp(self) -> None:
        if self.mcp is not None:
            self.mcp.stop()

    def _stop_engine(self) -> None:
        if self.engine is not None:
            self.engine.stop()

    def _on_any_state_change(self, old_state: str, new_state: str) -> None:
        try:
            self.on_state_refresh()
        except Exception:  # noqa: BLE001 — a UI refresh must never crash a supervisor
            pass

    def _on_engine_state_change(self, old_state: str, new_state: str) -> None:
        """Keep the *window* honest about the engine, not just the menu bar. An automatic
        restart re-binds a fresh port and a fresh CSRF session, so the page loaded before
        the crash is dead even though the menu row says "running" — reload it. And a
        mid-session ERROR must take over the window; a status row in a menu the user has
        never opened is not a visible failure."""
        try:
            if new_state == SidecarSupervisor.RUNNING and self._panel_loaded:
                self.logger.info("engine is RUNNING again — reloading the panel window")
                self._load_panel_url()
            elif new_state == SidecarSupervisor.ERROR:
                self._show_engine_error()
        except Exception:  # noqa: BLE001 — window upkeep must never crash a supervisor
            # ... but it must never fail SILENTLY either: this exact swallow hid why a
            # restarted engine's window stayed frozen in the field (2026-07-02).
            self.logger.exception("window upkeep after engine state change failed")
        self._on_any_state_change(old_state, new_state)

    # ---- window content -------------------------------------------------------
    def _load_panel_url(self) -> None:
        data = runtime_state.read_runtime_file("engine")
        if data is None or self._window is None:
            self.logger.warning(
                "cannot load the panel URL (%s) — showing the engine-error page",
                "no engine runtime file" if data is None else "no window attached")
            self._show_engine_error()
            return
        self._window.load_url(data["url"])
        self._panel_loaded = True

    def _show_no_project(self) -> None:
        self._panel_loaded = False   # the window no longer shows the panel
        if self._window is not None:
            self._window.load_html(_NO_PROJECT_HTML)

    def _show_engine_error(self) -> None:
        self._panel_loaded = False   # the window no longer shows the panel
        if self._window is not None:
            self._window.load_html(_ENGINE_ERROR_HTML)

    # ---- menu-bar actions -------------------------------------------------------
    def open_panel(self) -> None:
        # The window may be hidden (closing it hides, never quits — pilot finding
        # 2026-07-11: "Apple takes the app away always when I close it"). Show it
        # first, then load the panel only if it isn't already showing one — a
        # needless reload would throw away the researcher's place in the review.
        if self._window is not None:
            try:
                self._window.show()
            except Exception:  # noqa: BLE001 — some backends lack show(); loading still works
                pass
        if (self.engine is not None and self.engine.state == SidecarSupervisor.RUNNING
                and not self._panel_loaded):
            self._load_panel_url()

    def choose_project_folder(self) -> None:
        chosen = self._pick_folder()
        if not chosen:
            return
        self._stop_mcp()
        self._stop_engine()
        self._activate_root(chosen)
        if not self._wait_for_engine_running():
            self._show_engine_error()
            return
        self._load_panel_url()
        if appprefs.get_mcp_autostart():
            self._start_mcp()

    def toggle_mcp(self) -> None:
        """Start/stop the agent server. Consent lives HERE — at the moment of intent —
        not in a first-launch prompt (a modal before the user has rated a single claim
        can't produce an informed answer). The pref stays tri-state: ``None`` means the
        dialog was never accepted, so declining persists nothing and a later "Start Agent
        Server" click simply asks again; only an actual choice is ever written."""
        wanted = self.mcp is not None and self.mcp.state in (
            SidecarSupervisor.RUNNING, SidecarSupervisor.STARTING, SidecarSupervisor.ERROR)
        if wanted:
            appprefs.set_mcp_autostart(False)
            self._stop_mcp()
        else:
            if appprefs.get_mcp_autostart() is None and not self._ask_mcp_consent():
                return
            appprefs.set_mcp_autostart(True)
            self._start_mcp()

    def copy_mcp_connection_info(self) -> bool:
        url = self.mcp_connection_url()
        if url is None:
            return False
        _copy_to_clipboard(url)
        return True

    def restart_engine(self) -> None:
        if self.engine is not None:
            self.engine.restart()

    def restart_mcp(self) -> None:
        if self.mcp is not None:
            self.mcp.restart()
        else:
            self.toggle_mcp()   # never started this session — route through the consent gate

    def open_logs_folder(self) -> None:
        try:
            import subprocess
            # noqa justified: fixed literal executable ("open"), the only dynamic arg is
            # our own log directory path (never user/network input), no shell involved.
            subprocess.Popen(["open", str(paths.log_dir())])  # noqa: S603, S607
        except Exception:
            pass

    # ---- shutdown ----------------------------------------------------------
    def quit(self) -> None:
        """Idempotent, and always in dependency order: MCP first, then the engine — an
        agent call mid-panel-shutdown is worse than the panel outliving the agent server
        by a moment."""
        if self._quit_started:
            return
        self._quit_started = True
        self.logger.info("quitting — stopping the agent server, then the panel engine")
        self._stop_mcp()
        self._stop_engine()


def make_close_handler(shell: CiteVahtiShell, window) -> Callable[[], bool]:
    """The window's ``closing`` handler: **hide, don't quit**. CiteVahti is a menu-bar
    app — closing the window used to run ``shell.quit()`` (stopping both sidecars) and
    let pywebview's loop exit with its last window, so every close cost a cold restart
    (pilot finding, 2026-07-11: "Apple takes the app away always when I close it").
    Returning False cancels the close after hiding; "Open Review Panel" in the menu bar
    brings the same window back with the researcher's place intact. A real quit (menu
    Quit, Cmd+Q → the will-terminate observer, atexit) still stops the sidecars — and
    while it is underway the close is allowed through so termination is never blocked."""
    def _on_closing() -> bool:
        if shell._quit_started:
            return True
        try:
            window.hide()
        except Exception:  # noqa: BLE001 — a backend without hide() falls back to closing
            return True
        return False
    return _on_closing


def _native_consent_dialog() -> bool:
    """The "let an AI assistant connect?" consent prompt, shown from the "Start Agent
    Server" menu action — i.e. on the Cocoa main thread (NSAlert is main-thread-only; do
    not call this from a supervisor or pywebview worker thread). Best-effort PyObjC; any
    failure (headless test run, missing AppKit) defaults to the safe answer: don't enable.

    The wording states only what ``agent/policy.py`` actually enforces — the assistant
    can search, stage evidence, and give its own rating (recorded blind), but it can never
    rate for you, apply a change without your approval, or make the final call. It must
    not claim more (e.g. "nothing is recorded until you rate") than the engine guarantees.
    """
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSAlert, NSAlertFirstButtonReturn
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Let an AI assistant connect to CiteVahti?")
        alert.setInformativeText_(
            "A chat assistant (like Claude) will be able to help screen citations: search, "
            "stage evidence, and give its own rating — recorded blind, hidden from you "
            "until you have rated. It can never rate for you, change anything without "
            "your approval, or make the final call. This runs only on this computer, and "
            "you can turn it off anytime from the CiteVahti menu-bar icon.")
        alert.addButtonWithTitle_("Enable")
        alert.addButtonWithTitle_("Not Now")
        return alert.runModal() == NSAlertFirstButtonReturn
    except Exception:
        return False


def _dispatch_on_main(fn: Callable[[], None]) -> None:
    """Run ``fn`` on the Cocoa main thread. AppKit (NSStatusBar, NSAlert, menu mutation)
    is main-thread-only, but pywebview invokes its ``start()`` callback — where the menu
    bar is built and supervisor state changes arrive — on a background thread; calling
    AppKit there is undefined behaviour that may render fine on one machine and freeze or
    crash on another. Off macOS (or without PyObjC) this degrades to a direct call, which
    is correct for the guarded no-op shims and for headless tests."""
    if sys.platform != "darwin":
        fn()
        return
    try:
        from PyObjCTools import AppHelper
        AppHelper.callAfter(fn)
    except Exception:  # noqa: BLE001 — no PyObjC means the AppKit shims no-op anyway
        fn()


def _copy_to_clipboard(text: str) -> None:
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSPasteboard, NSStringPboardType
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSStringPboardType)
    except Exception:
        pass


# ---- menu bar (PyObjC, macOS-only, best-effort — see the module docstring) ---
def _build_menu_bar(shell: CiteVahtiShell):
    if sys.platform != "darwin":
        return None
    try:
        import objc
        from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength
        from Foundation import NSObject

        class _MenuTarget(NSObject):
            def initWithShell_(self, shell):
                self = objc.super(_MenuTarget, self).init()
                if self is None:
                    return None
                self.shell = shell
                return self

            def openPanel_(self, sender):
                self.shell.open_panel()

            def chooseFolder_(self, sender):
                self.shell.choose_project_folder()

            def toggleMcp_(self, sender):
                self.shell.toggle_mcp()

            def copyMcpInfo_(self, sender):
                self.shell.copy_mcp_connection_info()

            def restartEngine_(self, sender):
                self.shell.restart_engine()

            def restartMcp_(self, sender):
                self.shell.restart_mcp()

            def openLogsFolder_(self, sender):
                self.shell.open_logs_folder()

            def quitApp_(self, sender):
                self.shell.quit()
                from AppKit import NSApp
                NSApp.terminate_(sender)

        target = _MenuTarget.alloc().initWithShell_(shell)
        status_bar = NSStatusBar.systemStatusBar()
        item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        item.setTitle_("CiteVahti")
        item.setHighlightMode_(True)
        menu = NSMenu.alloc().init()

        panel_status = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Panel: starting", None, "")
        panel_status.setEnabled_(False)
        agent_status = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Agent server: stopped", None, "")
        agent_status.setEnabled_(False)
        menu.addItem_(panel_status)
        menu.addItem_(agent_status)
        menu.addItem_(_separator())

        def _item(title, action):
            mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            mi.setTarget_(target)
            menu.addItem_(mi)
            return mi

        _item("Open Review Panel", "openPanel:")
        mcp_info_item = _item("Copy MCP Connection Info", "copyMcpInfo:")
        toggle_item = _item("Start Agent Server", "toggleMcp:")
        _item("Restart Panel Engine", "restartEngine:")
        _item("Choose Project Folder…", "chooseFolder:")
        _item("Open Logs Folder", "openLogsFolder:")
        menu.addItem_(_separator())
        _item("Quit", "quitApp:")

        item.setMenu_(menu)

        def refresh() -> None:
            state = shell.app_state
            panel_status.setTitle_(f"Panel: {_PANEL_LABELS.get(state, 'unknown')}")
            agent_running = shell.mcp is not None and shell.mcp.state == SidecarSupervisor.RUNNING
            agent_status.setTitle_(
                f"Agent server: {_AGENT_LABELS.get(state, 'stopped')} — "
                "running locally on 127.0.0.1" if agent_running else
                f"Agent server: {_AGENT_LABELS.get(state, 'stopped')}")
            mcp_info_item.setEnabled_(shell.mcp_connection_url() is not None)
            toggle_item.setTitle_("Stop Agent Server" if agent_running
                                   else "Start Agent Server")

        # Supervisor monitor threads drive state changes; menu mutation must hop to main.
        shell.on_state_refresh = lambda: _dispatch_on_main(refresh)
        refresh()   # _build_menu_bar itself runs on the main thread (see run_app)
        return item
    except Exception:
        return None


def _separator():
    from AppKit import NSMenuItem
    return NSMenuItem.separatorItem()


_PANEL_LABELS = {
    NO_PROJECT: "no project selected", STARTING_ENGINE: "starting",
    PANEL_READY: "running", STARTING_AGENT: "running", READY: "running",
    DEGRADED_PANEL_ERROR: "had trouble starting — try Restart", STOPPING: "stopping",
}
_AGENT_LABELS = {
    STARTING_AGENT: "starting", READY: "running",
    DEGRADED_AGENT_ERROR: "had trouble starting — try Restart", STOPPING: "stopping",
}


def _install_quit_observer(shell: CiteVahtiShell) -> None:
    """A belt-and-suspenders hook for Cmd+Q / Dock "Quit" — an ``NSNotificationCenter``
    observer rather than replacing ``NSApplication``'s delegate, so this never competes
    with pywebview's own app delegate for the single delegate slot."""
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSObject, NSNotificationCenter

        class _QuitObserver(NSObject):
            def handleWillTerminate_(self, notification):
                shell.quit()

        observer = _QuitObserver.alloc().init()
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            observer, "handleWillTerminate:", "NSApplicationWillTerminateNotification", None)
        shell._quit_observer = observer   # keep a strong reference alive
    except Exception:
        pass


def _import_webview():
    """Import pywebview, or raise a clear, actionable error (no terminal jargon)."""
    try:
        import webview  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only when the extra is absent
        raise RuntimeError(
            "the desktop window needs pywebview — install it with: "
            "pip install 'citevahti[app]'") from exc
    return webview


def _icon_path() -> Optional[str]:
    """The packaged window/app icon if it ships alongside the install, else None."""
    p = Path(__file__).resolve().parent / "panel" / "web" / "apple-touch-icon.png"
    return str(p) if p.is_file() else None


def _announce_update() -> None:
    """On launch, check for a signed update and surface it — without blocking or auto-
    applying. Inert (a no-op) until the auto-updater is configured."""
    try:
        from .autoupdate import check_for_update

        outcome = check_for_update()
        if outcome.update_available:
            print(f"A newer CiteVahti is available ({outcome.version}). "
                  "Use 'Check for updates' to install it.")
    except Exception:  # pragma: no cover — the updater must never break a launch
        pass


def run_app(*, webview=None,
            engine_supervisor_factory=_default_engine_supervisor,
            mcp_supervisor_factory=_default_mcp_supervisor,
            folder_picker: Optional[Callable[[], Optional[str]]] = None,
            consent_prompt: Optional[Callable[[], bool]] = None,
            shell_factory=CiteVahtiShell) -> int:
    """Open the CiteVahti.app shell: a pywebview window + (on macOS) a menu-bar icon,
    supervising the ``citevahti-engine`` and, if enabled, ``citevahti-mcp`` sidecars.
    Blocks until the window/app quits. Returns a process exit code.
    """
    _announce_update()
    wv = webview or _import_webview()
    shell = shell_factory(
        webview=wv, engine_supervisor_factory=engine_supervisor_factory,
        mcp_supervisor_factory=mcp_supervisor_factory,
        folder_picker=folder_picker, consent_prompt=consent_prompt)

    # macOS shows the menu-bar/Dock name from the bundle — which is "Python" when run via
    # the interpreter (not a packaged .app). Relabel it to CiteVahti. No-op off macOS or
    # when pyobjc isn't present; never blocks a launch.
    try:
        from Foundation import NSBundle  # ships with pyobjc, a pywebview macOS dependency

        info = NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = "CiteVahti"
    except Exception:  # noqa: S110 — cosmetic only; a missing relabel must never break launch
        pass

    window = wv.create_window(_TITLE, html=_STARTING_HTML, width=1180, height=820,
                               min_size=(900, 600))
    shell.attach_window(window)
    atexit.register(shell.quit)
    try:
        window.events.closing += make_close_handler(shell, window)
    except Exception:
        pass

    def _on_started() -> None:
        # pywebview runs this on a background thread. The AppKit pieces hop to the main
        # thread; the boot itself (which blocks up to ~35s waiting on the engine) must
        # stay OFF the main thread or the whole UI beachballs during startup.
        _dispatch_on_main(lambda: _build_menu_bar(shell))
        _dispatch_on_main(lambda: _install_quit_observer(shell))
        shell.on_started()

    icon = _icon_path()
    try:
        wv.start(_on_started, icon=icon) if icon else wv.start(_on_started)
    except TypeError:
        wv.start(_on_started)
    return 0


def main(argv=None) -> int:
    return run_app()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
