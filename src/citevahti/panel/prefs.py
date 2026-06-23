"""Panel-local UI state (ADR-0007) — never part of the audited ledger.

Two stores, both plain JSON, no secrets:

- per-root ``<root>/.citevahti/panel.json`` — the bound manuscripts folder and the
  document-edit transactions/backups for that project.
- a single ``~/.config/citevahti/state.json`` — the last-used root, so the panel
  stops defaulting to an empty ledger (the "panel is blank" onboarding trap).

Kept out of ``config.json`` (which is audited and carries credential identifiers)
and out of the keyring (no secrets here)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

# ledgers the panel will look in when the active root is empty (onboarding aid)
_DISCOVER_DIRS = ("~/.citevahti", "~/Documents/CiteVahti/.citevahti", "./.citevahti")


def _global_state_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "citevahti" / "state.json"


def _panel_path(root: str) -> Path:
    return Path(root).expanduser() / ".citevahti" / "panel.json"


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---- per-root panel state ---------------------------------------------------
def load_panel(root: str) -> dict:
    return _read_json(_panel_path(root))


def save_panel(root: str, data: dict) -> None:
    _write_json(_panel_path(root), data)


def get_manuscripts_dir(root: str) -> Optional[str]:
    return load_panel(root).get("manuscripts_dir")


def set_manuscripts_dir(root: str, manuscripts_dir: str) -> None:
    data = load_panel(root)
    data["manuscripts_dir"] = str(Path(manuscripts_dir).expanduser())
    save_panel(root, data)


def remember_manuscript(root: str, manuscript_id: Optional[str]) -> None:
    """Record the manuscript being worked on, so a reload returns to it instead of
    snapping back to the first (claims-heavy) one. Per-root; best-effort."""
    if not manuscript_id:
        return
    try:
        data = load_panel(root)
        data["active_manuscript"] = manuscript_id
        save_panel(root, data)
    except OSError:
        pass


def recall_manuscript(root: str) -> Optional[str]:
    return load_panel(root).get("active_manuscript")


# ---- remembered root (global) ----------------------------------------------
def remember_root(root: str) -> None:
    try:
        _write_json(_global_state_path(), {"last_root": str(Path(root).expanduser().resolve())})
    except OSError:
        pass   # remembering is best-effort; never block startup


def recall_root() -> Optional[str]:
    r = _read_json(_global_state_path()).get("last_root")
    return r if r and (Path(r) / ".citevahti").is_dir() else None


def has_ledger(root: str) -> bool:
    return (Path(root).expanduser() / ".citevahti").is_dir()


def resolve_default_root(cli_root: Optional[str]) -> str:
    """Pick the root for the panel when ``--root`` is omitted.

    Precedence: explicit ``--root`` → ``$CITEVAHTI_ROOT`` → the cwd if it has a
    ledger → the last-used root → cwd. This is what stops the empty-``~/.citevahti``
    trap without surprising someone who deliberately passes ``--root``."""
    if cli_root and cli_root != ".":
        return cli_root
    env = os.environ.get("CITEVAHTI_ROOT")
    if env and has_ledger(env):
        return env
    if has_ledger("."):
        return str(Path(".").resolve())
    remembered = recall_root()
    if remembered:
        return remembered
    return cli_root or "."


# ---- ledger discovery (empty-state onboarding) ------------------------------
def discover_ledgers(active_root: Optional[str] = None) -> list[dict]:
    """Find ledgers in the usual places and count their claims, so the empty-state
    screen can offer a one-click switch to a populated one."""
    seen: set[str] = set()
    out: list[dict] = []
    candidates = list(_DISCOVER_DIRS)
    if active_root:
        candidates.insert(0, str(Path(active_root).expanduser() / ".citevahti"))
    for d in candidates:
        ledger = Path(d).expanduser()
        try:
            ledger = ledger.resolve()
        except OSError:
            continue
        if not ledger.is_dir() or str(ledger) in seen:
            continue
        seen.add(str(ledger))
        claims_dir = ledger / "claims"
        n = len(list(claims_dir.glob("claim-*.json"))) if claims_dir.is_dir() else 0
        out.append({"root": str(ledger.parent), "ledger": str(ledger), "claims": n})
    return out
