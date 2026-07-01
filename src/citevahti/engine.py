"""``citevahti-engine`` — the review-panel sidecar, supervised by the desktop app shell.

Wraps the existing, unchanged ``start.launch_panel()`` (loopback-only) in a standalone
process the shell can spawn, health-check, restart on crash, and cleanly stop — a thread
inside the shell's own process can't be `poll()`'d or killed independently, which is why
this is a separate executable rather than more in-process threading.

On a successful bind it publishes its actual URL/pid/root into
``~/.config/citevahti/runtime/engine.json`` (see ``runtime_state.py``) so the shell never
has to guess a port, and it shuts down cleanly on ``SIGTERM``/``SIGINT`` (the shell's normal
way of stopping it, and also what a plain ``kill`` sends).
"""

from __future__ import annotations

import os
import signal
import threading
from datetime import datetime, timezone

from . import __version__, applog, runtime_state
from .rootcfg import resolve_root
from .start import launch_panel

_RUNTIME_NAME = "engine"


def _install_signal_handlers(stop_event: threading.Event) -> None:
    def _handler(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="citevahti-engine",
        description="Run the CiteVahti review panel as a supervised sidecar (loopback only).")
    parser.add_argument("--root", default=None,
                        help="project root holding .citevahti/ (default: the usual "
                             "CiteVahti root resolution)")
    parser.add_argument("--port", type=int, default=8765,
                        help="preferred panel port; falls back to an available loopback "
                             "port if it's held by something that isn't a CiteVahti panel")
    args = parser.parse_args(argv)

    root = resolve_root(args.root)
    logger = applog.get_logger("engine")
    logger.info(f"citevahti-engine v{__version__}: root={root}")

    result = launch_panel(root, port=args.port, host="127.0.0.1", open_browser=False)
    if result["status"] == "refused_non_loopback":
        # Can't happen — host is hardcoded above, never a flag — but never trust a single
        # layer for a safety invariant.
        logger.error("refused a non-loopback host (this should be unreachable)")
        return 2
    if result["status"] == "port_conflict":
        logger.error(f"port {args.port} is occupied by a non-CiteVahti service; not starting")
        return 2

    httpd = result["_httpd"]
    url = result["url"]
    logger.info(f"panel {result['status']} at {url}")
    runtime_state.write_runtime_file(
        _RUNTIME_NAME, url=url, pid=os.getpid(), root=root,
        started_at=datetime.now(timezone.utc).isoformat())

    stop_event = threading.Event()
    _install_signal_handlers(stop_event)
    stop_event.wait()

    logger.info("shutting down")
    if httpd is not None:
        httpd.shutdown()
        httpd.server_close()
    runtime_state.clear_runtime_file(_RUNTIME_NAME)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
