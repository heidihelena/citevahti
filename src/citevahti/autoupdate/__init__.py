"""Secure auto-updates for the CiteVahti **desktop app** (the PyInstaller bundle).

Built on `tufup` → `python-tuf` (The Update Framework): updates are delivered as
signed metadata + hashes, so a client accepts a new version only if it was signed
by CiteVahti's offline keys — authenticity and integrity **even if the update
server is compromised**. See `docs/AUTO_UPDATE.md`.

This is distinct from `citevahti.update_check` (a lightweight "newer version on
PyPI?" nudge for the pip install). Auto-update applies to the *frozen* desktop app.

**Inert until configured.** With no update URL and no bundled trusted root (the
state until the founder generates the offline keys and stands up the update
server), every entry point here is a safe no-op — it never breaks a launch and
never touches the network. Nothing is ever auto-applied silently: the caller
checks, the human is prompted, and only then is an update downloaded and applied.
"""

from .client import UpdateOutcome, apply_update, check_for_update
from .settings import AutoUpdateSettings, resolve_settings

__all__ = [
    "AutoUpdateSettings",
    "resolve_settings",
    "check_for_update",
    "apply_update",
    "UpdateOutcome",
]
