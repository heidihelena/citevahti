"""Client side of the auto-updater: check for, and apply, a signed update.

Every entry point is **safe**: if the updater isn't configured (the default until
keys exist) it returns a `not_configured` outcome without importing tufup or
touching the network; any tufup/network error degrades to `unavailable` with a
reason. Nothing here ever raises to the caller, and `apply_update` is only ever
reached after an explicit decision — there is no silent self-update.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from .settings import AutoUpdateSettings, resolve_settings

# status values an integration can branch on
NOT_CONFIGURED = "not_configured"   # inert: no URL / no root / not frozen
UP_TO_DATE = "up_to_date"
AVAILABLE = "available"
APPLIED = "applied"
UNAVAILABLE = "unavailable"         # configured, but the check/apply couldn't complete


@dataclass(frozen=True)
class UpdateOutcome:
    status: str
    version: Optional[str] = None   # the available/applied version, when known
    detail: Optional[str] = None

    @property
    def update_available(self) -> bool:
        return self.status == AVAILABLE


class _TufupClient(Protocol):
    """The slice of tufup's Client that this module uses — so the duck-typed seam
    (real tufup Client in production, a fake in tests) is checked at the call sites."""

    def check_for_updates(self) -> Any: ...

    def download_and_apply_update(self, *, skip_confirmation: bool = ...,
                                  progress_hook: Optional[Callable[[float], None]] = ...,
                                  install: Callable[..., Any] = ...) -> Any: ...


# A factory returning a tufup-Client-like object. Injectable so tests never need tufup
# or a network.
ClientFactory = Callable[[AutoUpdateSettings], _TufupClient]


def _default_client_factory(s: AutoUpdateSettings) -> _TufupClient:
    """Build a real tufup Client, bootstrapping the trusted root on first run."""
    from tufup.client import Client  # lazy: only when actually configured

    s.metadata_dir.mkdir(parents=True, exist_ok=True)
    s.target_dir.mkdir(parents=True, exist_ok=True)
    # tufup bootstraps trust from a root.json already present in metadata_dir; seed it
    # from the copy bundled with the app the first time.
    root_dst = s.metadata_dir / "root.json"
    if not root_dst.is_file() and s.trusted_root is not None:
        shutil.copyfile(s.trusted_root, root_dst)

    return Client(
        app_name=s.app_name,
        app_install_dir=s.install_dir,
        current_version=s.current_version,
        metadata_dir=s.metadata_dir,
        metadata_base_url=s.metadata_base_url,
        target_dir=s.target_dir,
        target_base_url=s.target_base_url,
        refresh_required=False,
    )


def check_for_update(
    settings: Optional[AutoUpdateSettings] = None,
    *,
    client_factory: Optional[ClientFactory] = None,
) -> UpdateOutcome:
    """Is a newer, signed bundle available? Read-only — never applies anything."""
    s = settings or resolve_settings()
    if not s.is_configured():
        return UpdateOutcome(NOT_CONFIGURED, detail=s.why_inert())
    try:
        client = (client_factory or _default_client_factory)(s)
        new = client.check_for_updates()  # tufup: TargetMeta or None
    except Exception as exc:  # noqa: BLE001 — a flaky server must not crash the app
        return UpdateOutcome(UNAVAILABLE, detail=f"update check failed: {exc}")
    if not new:
        return UpdateOutcome(UP_TO_DATE, version=s.current_version)
    return UpdateOutcome(AVAILABLE, version=str(getattr(new, "version", "")) or None)


def apply_update(
    settings: Optional[AutoUpdateSettings] = None,
    *,
    client_factory: Optional[ClientFactory] = None,
    progress_hook: Optional[Callable[[float], None]] = None,
) -> UpdateOutcome:
    """Download + apply the available signed update. Call ONLY after the human has
    agreed — this is the post-consent step, never invoked automatically."""
    s = settings or resolve_settings()
    if not s.is_configured():
        return UpdateOutcome(NOT_CONFIGURED, detail=s.why_inert())
    try:
        client = (client_factory or _default_client_factory)(s)
        new = client.check_for_updates()
        if not new:
            return UpdateOutcome(UP_TO_DATE, version=s.current_version)
        # skip tufup's own prompt: consent is the caller's responsibility (the app's
        # prompted-update UX). Don't auto-restart here — let the app decide.
        client.download_and_apply_update(
            skip_confirmation=True,
            progress_hook=progress_hook,
            install=_no_restart_install,
        )
    except Exception as exc:  # noqa: BLE001
        return UpdateOutcome(UNAVAILABLE, detail=f"update apply failed: {exc}")
    return UpdateOutcome(APPLIED, version=str(getattr(new, "version", "")) or None)


def _no_restart_install(src_dir, dst_dir, **_kwargs) -> None:
    """Replace the install in place WITHOUT auto-restarting — the app controls restart
    (so a review in progress is never killed from under the user)."""
    import os

    for entry in os.listdir(src_dir):
        s = os.path.join(src_dir, entry)
        d = os.path.join(dst_dir, entry)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
