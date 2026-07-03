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
from pathlib import Path
from typing import Optional

# ledgers the panel will look in when the active root is empty (onboarding aid)
_DISCOVER_DIRS = ("~/.citevahti", "~/Documents/CiteVahti/.citevahti", "./.citevahti")


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


# ---- remembered root + the shared resolver ---------------------------------
# The last-used root and the resolver now live in `rootcfg` so every surface — the
# CLI, the MCP server, and this panel — answers "what am I working on" the same way.
# Re-exported here so existing `prefs.*` call sites keep working.
from ..rootcfg import has_ledger, recall_root, remember_root, resolve_root  # noqa: E402,F401


def resolve_default_root(cli_root: Optional[str]) -> str:
    """The panel's project root — now the one shared resolver (see ``rootcfg``)."""
    return resolve_root(cli_root)


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
        # last-activity time for a "Your reviews" recency label: the audit log is touched on
        # every event, so it tracks real work better than the directory mtime.
        audit = ledger / "audit_log.jsonl"
        try:
            mtime = (audit if audit.exists() else ledger).stat().st_mtime
        except OSError:
            mtime = 0.0
        out.append({"root": str(ledger.parent), "ledger": str(ledger), "claims": n, "mtime": mtime})
    return out


def get_auto_update_check(root: str) -> bool:
    """Opt-in, default OFF: whether the panel may make ONE update check against PyPI
    when it opens. Off = the documented no-launch-time-phone-home posture; turning it
    on is an explicit, disclosed choice made in the Settings surface."""
    return bool(load_panel(root).get("auto_update_check", False))


def set_auto_update_check(root: str, enabled: bool) -> None:
    data = load_panel(root)
    data["auto_update_check"] = bool(enabled)
    save_panel(root, data)
