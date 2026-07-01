"""Parent-death watchdog for supervised sidecars — exit when the shell dies.

A sidecar spawned by CiteVahti.app must never outlive the shell. If the shell dies
without running its clean quit path (Force Quit, a crash in the GUI layer, a plain
``kill -9``), the child is re-parented (to launchd on macOS, pid 1 elsewhere) and keeps
serving invisibly — an agent server the user believes is off, answering on a port their
chat client is still configured for, against a project root that may no longer be the
active one. Polling ``os.getppid()`` catches re-parenting cheaply and portably.

On detecting an orphaning, the watchdog triggers the sidecar's *own* ``SIGTERM`` path
(so its normal cleanup — runtime-file removal, server shutdown — runs), then hard-exits
as a backstop if the process is somehow still alive after a grace period.

Opt-in: only the shell passes ``--parent-pid``. A standalone dev run, the plain CLI, and
the Claude Desktop stdio ``.mcpb`` never enable it and are unaffected.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from typing import Callable, Optional


def _default_terminate() -> None:
    os.kill(os.getpid(), signal.SIGTERM)


def _default_hard_exit() -> None:
    os._exit(1)


def watch_parent(
    parent_pid: int,
    *,
    poll_interval: float = 2.0,
    grace: float = 10.0,
    getppid: Callable[[], int] = os.getppid,
    terminate: Optional[Callable[[], None]] = None,
    hard_exit: Optional[Callable[[], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> threading.Thread:
    """Start a daemon thread that ends this process once ``parent_pid`` is no longer our
    parent. Returns the thread (mostly for tests; production code fires and forgets).

    The daemon flag matters twice over: the watchdog must never keep an otherwise-exiting
    sidecar alive, and after ``terminate()`` triggers the sidecar's clean ``SIGTERM`` exit
    the backstop simply dies with the process instead of ever reaching ``hard_exit``.
    """
    do_terminate = terminate if terminate is not None else _default_terminate
    do_hard_exit = hard_exit if hard_exit is not None else _default_hard_exit

    def _loop() -> None:
        while getppid() == parent_pid:
            sleep(poll_interval)
        do_terminate()
        sleep(grace)
        do_hard_exit()

    thread = threading.Thread(target=_loop, name="citevahti-parentwatch", daemon=True)
    thread.start()
    return thread
