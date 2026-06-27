"""Where the auto-updater reads its configuration — and the gate that keeps it
inert until everything it needs actually exists.

The updater is *configured* only when all of these hold:
  - the app is running **frozen** (a PyInstaller bundle) — tufup updates a frozen
    app in place; a `pip` install updates with pip, not this;
  - an **update server URL** is set (`CITEVAHTI_UPDATE_URL`);
  - a **trusted root metadata** file (`root.json`) ships with the app — the trust
    anchor the client bootstraps from. It is created when the founder generates the
    offline keys (see `docs/AUTO_UPDATE.md`); until then there is none, so the
    updater stays a no-op.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

APP_NAME = "CiteVahti"


def _is_frozen() -> bool:
    """True when running inside a PyInstaller bundle (the only place tufup applies)."""
    return bool(getattr(sys, "frozen", False))


def _bundled_root() -> Optional[Path]:
    """The trusted `root.json` shipped with the app, if present. Built/placed only
    once the founder has generated keys; absent (→ updater inert) until then."""
    p = Path(__file__).resolve().parent / "root.json"
    return p if p.is_file() else None


def _install_dir() -> Path:
    """The directory holding the running app — where an applied update is unpacked."""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent  # non-frozen: never actually used


def _cache_dir() -> Path:
    """Per-user cache for the update metadata + downloaded targets (not the install)."""
    return Path.home() / ".citevahti" / "update"


@dataclass(frozen=True)
class AutoUpdateSettings:
    app_name: str
    current_version: str
    update_url: Optional[str]
    trusted_root: Optional[Path]
    install_dir: Path
    metadata_dir: Path
    target_dir: Path
    frozen: bool

    @property
    def metadata_base_url(self) -> Optional[str]:
        return f"{self.update_url.rstrip('/')}/metadata/" if self.update_url else None

    @property
    def target_base_url(self) -> Optional[str]:
        return f"{self.update_url.rstrip('/')}/targets/" if self.update_url else None

    def is_configured(self) -> bool:
        """All preconditions present → the updater may talk to the server. Until the
        founder generates keys + sets the URL, this is False and the updater is inert."""
        return bool(self.frozen and self.update_url and self.trusted_root)

    def why_inert(self) -> str:
        """A plain, honest reason the updater is doing nothing — for logs/UX."""
        if not self.frozen:
            return "not a frozen desktop app (pip installs update with pip)"
        if not self.update_url:
            return "no update server configured (CITEVAHTI_UPDATE_URL unset)"
        if not self.trusted_root:
            return "no trusted root metadata bundled (keys not generated yet)"
        return "configured"


def resolve_settings(current_version: Optional[str] = None) -> AutoUpdateSettings:
    """Build the settings from the environment + the running install. Pure aside from
    reading env/paths; never raises."""
    from .. import __version__

    cache = _cache_dir()
    return AutoUpdateSettings(
        app_name=APP_NAME,
        current_version=current_version or __version__,
        update_url=os.environ.get("CITEVAHTI_UPDATE_URL") or None,
        trusted_root=_bundled_root(),
        install_dir=_install_dir(),
        metadata_dir=cache / "metadata",
        target_dir=cache / "targets",
        frozen=_is_frozen(),
    )
