"""``supervisor.py`` — ``SidecarSupervisor``'s state machine, driven synchronously via
``check_once()`` with a fake ``Popen`` and a fake health probe (no real subprocess, socket,
or sleeping involved). A single end-to-end test at the bottom exercises the real background
thread with tiny real intervals to prove the threading glue itself is wired correctly.
"""

from __future__ import annotations

import os
import time

import pytest

from citevahti import runtime_state
from citevahti.supervisor import SidecarSupervisor


class FakePopen:
    """A scriptable stand-in for ``subprocess.Popen``: ``poll()`` returns ``None`` while
    ``alive`` is left true; set it to an int to simulate a crash exit code."""

    def __init__(self):
        self.alive = True
        self.exit_code = 1
        self.terminated = False
        self.killed = False
        self.wait_calls = []
        self.pid = None   # set an int to exercise the runtime-heartbeat identity check

    def poll(self):
        return None if self.alive else self.exit_code

    def terminate(self):
        self.terminated = True
        self.alive = False

    def kill(self):
        self.killed = True
        self.alive = False

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self.exit_code


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def _make(popens=None, health_probe=lambda: True, **kw):
    popens = list(popens) if popens is not None else [FakePopen()]
    it = iter(popens)
    kw.setdefault("clock", FakeClock())
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("max_restarts", 5)
    kw.setdefault("startup_timeout", 10.0)
    kw.setdefault("wedge_threshold", 3)
    sup = SidecarSupervisor(
        "engine", ["citevahti-engine"], health_probe,
        popen_factory=lambda cmd: next(it), **kw)
    return sup


def test_becomes_running_once_healthy():
    sup = _make(health_probe=lambda: True)
    sup._spawn()
    assert sup.state == sup.STARTING
    sup.check_once()
    assert sup.state == sup.RUNNING
    assert sup.attempt == 0


def test_never_healthy_restarts_then_settles_into_error_after_max_attempts():
    clock = FakeClock()
    popens = [FakePopen() for _ in range(8)]
    sup = _make(popens=popens, health_probe=lambda: False, clock=clock, max_restarts=5)
    sup._spawn()
    for _ in range(6):
        clock.advance(11)   # exceeds the 10s default startup_timeout each time
        sup.check_once()
    assert sup.state == sup.ERROR
    assert sup.attempt == 6


def test_crash_while_running_triggers_immediate_restart():
    p1, p2 = FakePopen(), FakePopen()
    sup = _make(popens=[p1, p2], health_probe=lambda: True)
    sup._spawn()
    sup.check_once()
    assert sup.state == sup.RUNNING
    p1.alive = False   # simulate a crash
    sup.check_once()
    assert sup.attempt == 1
    assert sup.state == sup.STARTING
    assert sup.process is p2


def test_wedge_after_three_consecutive_health_failures_kills_and_restarts():
    p1, p2 = FakePopen(), FakePopen()
    healthy = {"value": True}
    sup = _make(popens=[p1, p2], health_probe=lambda: healthy["value"], wedge_threshold=3)
    sup._spawn()
    sup.check_once()
    assert sup.state == sup.RUNNING
    healthy["value"] = False
    sup.check_once()   # 1st failure
    sup.check_once()   # 2nd failure
    assert p1.terminated is False
    sup.check_once()   # 3rd failure -> wedge
    assert p1.terminated is True
    assert sup.attempt == 1
    assert sup.state == sup.STARTING
    assert sup.process is p2


def test_manual_restart_resets_attempt_counter_from_error(monkeypatch):
    clock = FakeClock()
    popens = [FakePopen() for _ in range(8)]
    sup = _make(popens=popens, health_probe=lambda: False, clock=clock, max_restarts=5)
    sup._spawn()
    for _ in range(6):
        clock.advance(11)
        sup.check_once()
    assert sup.state == sup.ERROR

    monkeypatch.setattr(sup, "_start_monitor_thread", lambda: None)   # keep this test single-threaded
    sup.restart()
    assert sup.attempt == 0
    assert sup.state == sup.STARTING


def test_stop_terminates_then_settles_stopped():
    p = FakePopen()
    sup = _make(popens=[p])
    sup._spawn()
    sup.check_once()
    assert sup.state == sup.RUNNING
    sup.stop()
    assert p.terminated is True
    assert sup.state == sup.STOPPED


def test_stop_kills_when_terminate_does_not_exit_in_time():
    class HangingPopen(FakePopen):
        def wait(self, timeout=None):
            self.wait_calls.append(timeout)
            if not self.killed:
                import subprocess
                raise subprocess.TimeoutExpired(cmd="x", timeout=timeout)
            return self.exit_code

    p = HangingPopen()
    sup = _make(popens=[p])
    sup._spawn()
    sup.check_once()
    sup.stop()
    assert p.terminated is True
    assert p.killed is True
    assert sup.state == sup.STOPPED


def test_stop_is_idempotent():
    p = FakePopen()
    sup = _make(popens=[p])
    sup._spawn()
    sup.check_once()
    sup.stop()
    sup.stop()   # must not raise or re-terminate an already-gone process
    assert sup.state == sup.STOPPED


def test_on_state_change_callback_receives_transitions():
    transitions = []
    sup = _make(health_probe=lambda: True,
                on_state_change=lambda old, new: transitions.append((old, new)))
    sup._spawn()
    sup.check_once()
    assert (sup.NOT_STARTED, sup.STARTING) in transitions
    assert (sup.STARTING, sup.RUNNING) in transitions


def test_on_state_change_exception_does_not_crash_supervisor():
    def _boom(old, new):
        raise RuntimeError("ui callback exploded")

    sup = _make(health_probe=lambda: True, on_state_change=_boom)
    sup._spawn()
    sup.check_once()   # must not raise
    assert sup.state == sup.RUNNING


def test_stop_requested_during_backoff_prevents_a_respawn():
    """The quit-during-a-crash-loop race: if stop() is requested while _handle_failure is
    in its backoff sleep, the supervisor must NOT spawn a fresh sidecar afterwards — that
    child would be orphaned by the quitting app."""
    clock = FakeClock()
    popens = [FakePopen(), FakePopen()]
    sup = _make(popens=popens, health_probe=lambda: False, clock=clock,
                sleep=lambda s: sup._stop_flag.set())   # a concurrent stop() lands mid-backoff
    sup._spawn()
    clock.advance(11)   # exceed the startup timeout -> failure -> backoff -> (stop) -> ?
    sup.check_once()
    assert sup.process is popens[0]   # the second popen was never consumed


def test_default_backoff_sleep_is_interruptible_by_stop():
    """Production (no injected sleep) waits on the stop flag, so a pending stop() never
    sits behind a 30s time.sleep. With the flag pre-set, the 30s backoff returns at once."""
    clock = FakeClock()
    spawns = []

    def factory(cmd):
        spawns.append(cmd)
        return FakePopen()

    sup = SidecarSupervisor(
        "engine", ["citevahti-engine"], health_probe=lambda: False,
        popen_factory=factory, backoff_schedule=(30,), clock=clock)
    sup._spawn()
    sup._stop_flag.set()
    clock.advance(11)   # exceed the 10s default startup timeout
    t0 = time.monotonic()
    sup.check_once()   # startup timed out -> _handle_failure -> backoff "sleep"
    assert time.monotonic() - t0 < 5.0   # the 30s backoff was interrupted by the flag
    assert len(spawns) == 1   # and the post-stop respawn guard held


@pytest.mark.security
def test_probe_distrusts_a_foreign_runtime_heartbeat(tmp_path, monkeypatch):
    """After a Force Quit / shell crash, an orphaned sidecar's runtime handshake file is
    still live. Its heartbeat must not let a supervisor report its OWN child healthy —
    the handshake pid has to match the child the supervisor actually spawned."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdgcfg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    # The "orphan": a live pid (this test process) that is not the supervisor's child.
    runtime_state.write_runtime_file(
        "engine", url="http://127.0.0.1:1/orphan", pid=os.getpid(), root="/r",
        started_at="2026-07-01T00:00:00")
    p = FakePopen()
    p.pid = 424242   # our child's pid — not the one in the handshake file
    sup = _make(popens=[p], health_probe=lambda: True)
    sup._spawn()
    sup.check_once()
    assert sup.state == sup.STARTING   # a green probe wasn't enough: wrong heartbeat pid

    # Once the child itself owns the handshake, the same probe counts.
    p.pid = os.getpid()
    sup.check_once()
    assert sup.state == sup.RUNNING


def test_start_end_to_end_with_real_thread_reaches_running_then_stop(monkeypatch):
    p = FakePopen()
    sup = SidecarSupervisor(
        "engine", ["citevahti-engine"], health_probe=lambda: True,
        popen_factory=lambda cmd: p,
        startup_poll_interval=0.01, monitor_interval=0.01)
    sup.start()
    deadline = time.monotonic() + 2.0
    while sup.state != sup.RUNNING and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sup.state == sup.RUNNING
    sup.stop()
    assert sup.state == sup.STOPPED
    assert p.terminated is True
