"""Where the desktop app's runtime files live, and how it finds its own sidecar binaries.

One place to ask "where do I write" / "what do I exec" so ``applog.py``, ``appprefs.py``,
``runtime_state.py``, and the shell (``desktop.py``) agree. Concrete paths are macOS-first
(the desktop app is macOS-only today); the ``sys.platform`` branches for Windows/Linux are
cheap to keep correct now so this module doesn't need revisiting when those builds grow a
shell of their own.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def log_dir() -> Path:
    """Where the shell and sidecars write rotating log files."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "CiteVahti"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", "~/AppData/Local")).expanduser()
        return base / "CiteVahti" / "Logs"
    base = Path(os.environ.get("XDG_STATE_HOME", "~/.local/state")).expanduser()
    return base / "citevahti" / "log"


def config_dir() -> Path:
    """The app-level config directory — mirrors ``rootcfg.py``'s ``state.json`` location."""
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "citevahti"


def runtime_dir() -> Path:
    """Where sidecars publish their handshake files (``runtime_state.py``)."""
    return config_dir() / "runtime"


def bundled_binary(name: str) -> Path | None:
    """The path to a sibling frozen sidecar binary (e.g. ``citevahti-engine``) next to this
    process's own executable, or ``None`` when not running frozen (dev/test).

    The sidecars are built ``--onedir`` (``Contents/MacOS/<name>/<name>``, with the rest of
    the frozen payload alongside it as plain files) rather than ``--onefile``: a PyInstaller
    onefile binary re-extracts itself to a fresh temp directory on every launch, and on
    macOS that made a real, measured difference — Gatekeeper re-scanning that freshly
    written, unique-path payload on every single run turned every app launch into a ~50s
    hang, versus ~1s once the executable lives at a stable on-disk path. A flat sibling
    file (the older onefile layout) is still recognized as a fallback.
    """
    if not getattr(sys, "frozen", False):
        return None
    macos_dir = Path(sys.executable).resolve().parent
    onedir_candidate = macos_dir / name / name
    if onedir_candidate.is_file():
        return onedir_candidate
    onefile_candidate = macos_dir / name
    return onefile_candidate if onefile_candidate.is_file() else None


def dev_fallback_cmd(module: str) -> list[str]:
    """A ``python -m <module>`` command to run a sidecar from source (non-frozen dev/test
    runs) — ``module`` is a fully-qualified module path, e.g. ``"citevahti.engine"`` or
    ``"citevahti.agent.mcp_server"``."""
    return [sys.executable, "-m", module]
