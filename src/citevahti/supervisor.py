"""``SidecarSupervisor`` — generic subprocess lifecycle for a CiteVahti sidecar.

One class, instantiated twice by the shell (``desktop.py``): once for ``citevahti-engine``,
once for ``citevahti-mcp``. It owns spawning the child via an injectable ``popen_factory``,
polling an injectable ``health_probe`` for readiness, detecting a crash (``Popen.poll()``)
or a wedge (alive but the health probe stops answering), restarting with backoff up to a
cap, and a clean, idempotent ``stop()``. No PyObjC/pywebview import here — the whole point
is that this logic is testable with a fake ``Popen`` and a fake health probe, no real
subprocess or socket involved.

The state machine is deliberately split into a pure step (:meth:`check_once`, called
directly and repeatedly by tests with no sleeping) and a thin production loop
(:meth:`_run_loop`, a background thread that just calls ``check_once`` on an interval) — the
loop itself is trivial glue and isn't unit-tested; the transitions it drives are.
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Callable, Optional, Protocol, Sequence

from . import runtime_state


class _PopenLike(Protocol):
    """The slice of ``subprocess.Popen`` this module actually uses — narrow enough that a
    test's fake process object only needs these four methods, not a full ``Popen``."""

    def poll(self) -> Optional[int]: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: Optional[float] = None) -> int: ...


class SidecarSupervisor:
    NOT_STARTED = "not_started"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"

    def __init__(
        self,
        name: str,
        cmd: Sequence[str],
        health_probe: Callable[[], bool],
        *,
        popen_factory: Callable[[Sequence[str]], _PopenLike] = subprocess.Popen,
        on_state_change: Optional[Callable[[str, str], None]] = None,
        logger=None,
        runtime_name: Optional[str] = None,
        max_restarts: int = 5,
        backoff_schedule: Sequence[float] = (1, 2, 4, 8, 16, 30),
        startup_timeout: float = 10.0,
        startup_poll_interval: float = 0.3,
        monitor_interval: float = 1.0,
        wedge_threshold: int = 3,
        stop_timeout: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.name = name
        self.cmd = cmd
        self.health_probe = health_probe
        self.popen_factory = popen_factory
        self.on_state_change = on_state_change or (lambda old, new: None)
        self.logger = logger
        self.runtime_name = runtime_name or name
        self.max_restarts = max_restarts
        self.backoff_schedule = backoff_schedule
        self.startup_timeout = startup_timeout
        self.startup_poll_interval = startup_poll_interval
        self.monitor_interval = monitor_interval
        self.wedge_threshold = wedge_threshold
        self.stop_timeout = stop_timeout
        self._clock = clock
        self._sleep = sleep

        self.state = self.NOT_STARTED
        self.attempt = 0
        self.process: Optional[_PopenLike] = None
        self._consecutive_health_failures = 0
        self._spawned_at: Optional[float] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

    # ---- public lifecycle -----------------------------------------------------
    def start(self) -> None:
        """Idempotent — a no-op if already starting or running."""
        if self.state in (self.STARTING, self.RUNNING):
            return
        self.attempt = 0
        self._stop_flag.clear()
        self._spawn()
        self._start_monitor_thread()

    def restart(self) -> None:
        """Manual restart — resets the attempt counter even from ``ERROR``."""
        self.attempt = 0
        self._stop_flag.clear()
        self._terminate_process()
        self._spawn()
        self._start_monitor_thread()

    def stop(self) -> None:
        """Idempotent clean shutdown: terminate, wait, kill on timeout."""
        self._stop_flag.set()
        thread, self._monitor_thread = self._monitor_thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self.stop_timeout + 1)
        if self.state in (self.NOT_STARTED, self.STOPPED):
            return
        self._set_state(self.STOPPING)
        self._terminate_process()
        self.process = None
        runtime_state.clear_runtime_file(self.runtime_name)
        self._set_state(self.STOPPED)

    # ---- pure, directly-testable step ------------------------------------------
    def check_once(self) -> None:
        """One synchronous evaluation step. No sleeping — safe to call from a test loop."""
        if self.state == self.STARTING:
            self._check_starting()
        elif self.state == self.RUNNING:
            self._check_running()

    # ---- internals --------------------------------------------------------------
    def _set_state(self, new_state: str) -> None:
        if new_state == self.state:
            return
        old, self.state = self.state, new_state
        if self.logger is not None:
            self.logger.info(f"{self.name}: {old} -> {new_state}")
        try:
            self.on_state_change(old, new_state)
        except Exception:  # noqa: BLE001 — a UI callback must never crash the supervisor
            pass

    def _spawn(self) -> None:
        self.process = self.popen_factory(self.cmd)
        self._spawned_at = self._clock()
        self._consecutive_health_failures = 0
        self._set_state(self.STARTING)

    def _terminate_process(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=self.stop_timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=self.stop_timeout)

    def _probe_healthy(self) -> bool:
        try:
            return bool(self.health_probe())
        except Exception:  # noqa: BLE001 — a flaky probe must read as "not healthy yet"
            return False

    def _check_starting(self) -> None:
        if self.process is None or self._spawned_at is None:   # STARTING implies _spawn() ran
            raise RuntimeError("_check_starting called before _spawn()")
        if self.process.poll() is not None:
            self._handle_failure("crashed during startup")
            return
        if self._probe_healthy():
            self.attempt = 0
            self._set_state(self.RUNNING)
            return
        if self._clock() - self._spawned_at > self.startup_timeout:
            self._handle_failure("never became healthy within the startup timeout")

    def _check_running(self) -> None:
        if self.process is None:   # RUNNING implies _spawn() ran
            raise RuntimeError("_check_running called before _spawn()")
        if self.process.poll() is not None:
            self._handle_failure("crashed while running")
            return
        if self._probe_healthy():
            self._consecutive_health_failures = 0
            return
        self._consecutive_health_failures += 1
        if self._consecutive_health_failures >= self.wedge_threshold:
            self._terminate_process()
            self._handle_failure("wedged — health probe stopped responding")

    def _handle_failure(self, reason: str) -> None:
        self.attempt += 1
        if self.logger is not None:
            self.logger.warning(f"{self.name}: {reason} (attempt {self.attempt})")
        if self.attempt > self.max_restarts:
            self._set_state(self.ERROR)
            return
        idx = min(self.attempt - 1, len(self.backoff_schedule) - 1)
        self._sleep(self.backoff_schedule[idx])
        self._spawn()

    def _start_monitor_thread(self) -> None:
        self._monitor_thread = threading.Thread(
            target=self._run_loop, name=f"citevahti-supervisor-{self.name}", daemon=True)
        self._monitor_thread.start()

    def _run_loop(self) -> None:
        while not self._stop_flag.is_set() and self.state in (self.STARTING, self.RUNNING):
            self.check_once()
            interval = (self.startup_poll_interval if self.state == self.STARTING
                        else self.monitor_interval)
            self._sleep(interval)
