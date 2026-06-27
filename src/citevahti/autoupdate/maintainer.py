"""Maintainer side of the auto-updater — run by the founder, **offline**, at release
time. This is where the trust comes from, so it is deliberately a human-in-the-loop
local step, never CI (see the key split in `docs/AUTO_UPDATE.md`).

Two operations:
  - `init_repository(...)` — once: generate the TUF keys + initial signed metadata.
  - `add_release(...)`     — per release: add a frozen bundle as a signed target.

Key custody (the whole point of TUF): the `root` and `targets` private keys are the
trust anchors — keep them OFFLINE (an encrypted keystore dir on your machine, backed
up), never in CI. `snapshot`/`timestamp` are online roles that *may* later move to CI.
A leaked `root` key is the painful one to recover from — guard it accordingly.

tufup is an optional dependency (the `update` extra): `pip install 'citevahti[update]'`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .settings import APP_NAME


def _require_tufup():
    try:
        from tufup import repo as tufup_repo  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "the auto-update maintainer flow needs tufup — install it with: "
            "pip install 'citevahti[update]'") from exc
    return tufup_repo


# Injectable for tests; in production builds a real tufup Repository.
RepoFactory = Callable[..., object]


def _default_repo_factory(**kwargs) -> object:
    tufup_repo = _require_tufup()
    return tufup_repo.Repository(**kwargs)


def init_repository(
    repo_dir: str | Path,
    keys_dir: str | Path,
    *,
    app_name: str = APP_NAME,
    repo_factory: Optional[RepoFactory] = None,
) -> object:
    """One-time: create the TUF repo + generate the four role keys in `keys_dir`.

    Run this OFFLINE. Afterwards, back up `keys_dir` (especially `root` + `targets`)
    securely, and ship the generated `metadata/root.json` with the app (copy it to
    `src/citevahti/autoupdate/root.json`) — that bundled root is the client's trust
    anchor.
    """
    repo = (repo_factory or _default_repo_factory)(
        app_name=app_name,
        repo_dir=str(repo_dir),
        keys_dir=str(keys_dir),
    )
    repo.initialize()
    return repo


def add_release(
    repo_dir: str | Path,
    keys_dir: str | Path,
    bundle_dir: str | Path,
    version: str,
    *,
    app_name: str = APP_NAME,
    repo_factory: Optional[RepoFactory] = None,
) -> object:
    """Per release: add the frozen app bundle in `bundle_dir` as a signed target for
    `version`, then publish the updated, signed metadata.

    Run this OFFLINE with the `root`/`targets` keys in `keys_dir`. Upload the resulting
    `repo_dir/{metadata,targets}/` to the static update server (`CITEVAHTI_UPDATE_URL`).
    """
    repo = (repo_factory or _default_repo_factory)(
        app_name=app_name,
        repo_dir=str(repo_dir),
        keys_dir=str(keys_dir),
    )
    repo.add_bundle(new_bundle_dir=str(bundle_dir), new_version=version)
    repo.publish_changes(private_key_dirs=[str(keys_dir)])
    return repo
