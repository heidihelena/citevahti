"""``supervisor.py`` — ``SidecarSupervisor``'s state machine, driven synchronously via
``check_once()`` with a fake ``Popen`` and a fake health probe (no real subprocess, socket,
or sleeping involved). A single end-to-end test at the bottom exercises the real background
thread with tiny real intervals to prove the threading glue itself is wired correctly.
"""

from __future__ import annotations

import time


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
