"""``parentwatch.py`` — the sidecar parent-death watchdog, driven with an injected
``getppid``/``sleep``/``terminate``/``hard_exit`` so no real process is ever killed. The
control this guards: a sidecar spawned by the CiteVahti.app shell must never outlive it —
an orphaned agent server the user believes is off is a trust failure, not a leak of a
process (see SECURITY.md).
"""

from __future__ import annotations

import threading

import pytest

from citevahti.parentwatch import watch_parent

pytestmark = pytest.mark.security


def test_terminates_then_hard_exits_once_reparented():
    calls = []
    ppids = iter([100, 100, 1])   # parent alive twice, then re-parented to pid 1
    done = threading.Event()

    thread = watch_parent(
        100,
        getppid=lambda: next(ppids),
        sleep=lambda s: None,
        terminate=lambda: calls.append("terminate"),
        hard_exit=lambda: (calls.append("hard_exit"), done.set()),
    )
    assert done.wait(timeout=2.0)
    thread.join(timeout=2.0)
    assert calls == ["terminate", "hard_exit"]   # clean SIGTERM path first, backstop last


def test_stays_quiet_while_the_parent_is_alive():
    polled = threading.Event()
    finished = threading.Event()
    state = {"ppid": 100}
    calls = []

    def _sleep(seconds):
        polled.set()

    thread = watch_parent(
        100,
        getppid=lambda: state["ppid"],
        sleep=_sleep,
        terminate=lambda: calls.append("terminate"),
        hard_exit=lambda: (calls.append("hard_exit"), finished.set()),
    )
    assert polled.wait(timeout=2.0)   # the loop is running…
    assert calls == []                # …and has not fired while the parent matches

    state["ppid"] = 1                 # the shell dies
    assert finished.wait(timeout=2.0)
    thread.join(timeout=2.0)
    assert calls == ["terminate", "hard_exit"]


def test_watchdog_thread_is_a_daemon():
    # It must never keep an otherwise-exiting sidecar alive, and after a clean SIGTERM
    # exit the grace-period backstop should simply die with the process.
    state = {"ppid": 100}
    thread = watch_parent(100, getppid=lambda: state["ppid"],
                          sleep=lambda s: None, terminate=lambda: None,
                          hard_exit=lambda: None)
    assert thread.daemon is True
    state["ppid"] = 1   # let the loop finish so the thread doesn't outlive the test
    thread.join(timeout=2.0)
