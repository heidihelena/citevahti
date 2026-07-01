"""App-level shell preferences — ``~/.config/citevahti/app.json``.

Mirrors ``rootcfg.py``'s JSON-file convention (best-effort write, tolerant read) but is a
separate file: ``rootcfg.py``'s ``state.json`` is cross-surface "last-used project root";
this is shell-only preference, today holding exactly one setting.

``mcp_autostart`` is **tri-state**, not a plain bool: ``None`` means "never asked" (first
run — the shell should show the one-time consent prompt), ``True``/``False`` is the user's
persisted choice. A developer/test override via ``$CITEVAHTI_MCP_AUTOSTART`` short-circuits
the *read* path only — it never overwrites the persisted file, so a dev build doesn't
silently corrupt a real user's saved choice.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from . import paths

_ENV_OVERRIDE = "CITEVAHTI_MCP_AUTOSTART"


def _prefs_path() -> Path:
    return paths.config_dir() / "app.json"


def load_app_prefs() -> dict:
    """The persisted app-prefs dict, or ``{}`` if absent/unreadable."""
    try:
        return json.loads(_prefs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_app_prefs(data: dict) -> None:
    """Best-effort write; never blocks startup on a permissions error."""
    try:
        p = _prefs_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def get_mcp_autostart() -> Optional[bool]:
    """``True``/``False`` (persisted or dev-overridden), or ``None`` if never set."""
    override = os.environ.get(_ENV_OVERRIDE)
    if override is not None:
        return override.strip().lower() not in ("", "0", "false", "no")
    value = load_app_prefs().get("mcp_autostart")
    return value if isinstance(value, bool) else None


def set_mcp_autostart(value: bool) -> None:
    """Persist the user's answer to the "Enable AI agent server?" prompt."""
    data = load_app_prefs()
    data["mcp_autostart"] = bool(value)
    save_app_prefs(data)
