"""The sidecar handshake: ``~/.config/citevahti/runtime/<name>.json``.

A sidecar (``citevahti-engine`` or ``citevahti-mcp``) writes its *actual* bound URL, pid,
project root, and start time here right after it successfully binds — the shell never
guesses a port or assumes a fixed default; it reads this file. ``read_runtime_file`` only
returns a file whose ``pid`` is currently alive: a stale file left behind by a killed or
crashed sidecar (its own ``SIGTERM`` handler normally clears it, but a ``SIGKILL`` or a
crash wouldn't) must never be mistaken for "still running," so a dead pid is treated as
absent and the stale file is removed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from . import paths


def _path(name: str) -> Path:
    return paths.runtime_dir() / f"{name}.json"


def write_runtime_file(name: str, *, url: str, pid: int, root: str, started_at: str) -> None:
    """Best-effort write; a sidecar must never fail to start over a logging/state hiccup."""
    try:
        p = _path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"url": url, "pid": pid, "root": root, "started_at": started_at}, indent=2),
            encoding="utf-8")
    except OSError:
        pass


def _is_pid_alive(pid: object) -> bool:
    if not isinstance(pid, int):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # exists, just owned by someone else
    except OSError:
        return False
    return True


def read_runtime_file(name: str) -> Optional[dict]:
    """The handshake dict, or ``None`` if absent, unreadable, or its pid is no longer alive
    (a stale file is removed as a side effect, so the next check doesn't re-do this work)."""
    try:
        data = json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not _is_pid_alive(data.get("pid")):
        clear_runtime_file(name)
        return None
    return data


def clear_runtime_file(name: str) -> None:
    """Best-effort cleanup — called by a sidecar's own shutdown handler, and again by the
    supervisor as a belt-and-suspenders step after a forced kill."""
    try:
        _path(name).unlink()
    except OSError:
        pass
