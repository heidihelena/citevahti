"""Where the project ledger (``.citevahti/``) lives — resolved to a STABLE location.

Single-user and local-first. There is ONE resolver, ``resolve_root``, shared by every
surface (the CLI, the MCP server, and the loopback panel) so that "what am I working on"
has a single answer no matter how CiteVahti was launched. Previously the CLI/MCP fell back
to the home directory while the panel fell back to recents/cwd, so the same machine could
disagree with itself.

The precedence is:

1. an explicit ``--root`` (anything but ``"."``),
2. ``$CITEVAHTI_ROOT``,
3. the current directory **if it already holds a ledger** (you're clearly working here),
4. the last-used root **if it still holds a ledger** and isn't a leaked temp-dir
   ledger from an unisolated test run (so chat and panel agree),
5. the home directory.

Bare cwd is never the fallback: the MCP server is launched by the desktop app from an
arbitrary cwd (often ``/``), so a cwd-relative default would make ``init`` (run from home)
and the desktop-launched ``mcp-serve`` look at different places. cwd is honoured only when
it actually contains a ``.citevahti/`` ledger, which ``/`` does not.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

_STATE_DIRNAME = ".citevahti"   # mirrors state.store.STATE_DIRNAME (kept local: no import cycle)


def has_ledger(root: Optional[str]) -> bool:
    """True when ``root`` contains a ``.citevahti/`` ledger directory."""
    if not root:
        return False
    return (Path(root).expanduser() / _STATE_DIRNAME).is_dir()


# ---- the last-used root (global, cross-surface) -----------------------------
def _global_state_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "citevahti" / "state.json"


def _in_system_temp(path: Path) -> bool:
    """True when ``path`` lives in the system temp tree — ``tempfile.gettempdir()``,
    ``/tmp``, ``/var/tmp``, or macOS's per-user ``/var/folders/…``. Real projects never
    live there; test and e2e harnesses always do."""
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    # noqa rationale: nothing is stored at these paths — they only classify a
    # recorded root as temp-tree so it can be refused.
    for base in (Path(tempfile.gettempdir()), Path("/tmp"), Path("/var/tmp")):  # noqa: S108
        try:
            if resolved.is_relative_to(base.resolve()):
                return True
        except OSError:
            continue
    # macOS per-user temp: $TMPDIR points inside /var/folders but the exact directory
    # varies per boot/user, so a recorded path may not sit under the CURRENT
    # gettempdir() — match the fixed prefix instead.
    return str(resolved).startswith(("/private/var/folders/", "/var/folders/"))


def _leaked_temp_root(root: Path) -> bool:
    """A temp-tree root recorded in the REAL config is a leak: some e2e/test run drove
    the engine without isolating ``XDG_CONFIG_HOME``/``HOME``, and honouring it would
    silently open a throwaway test ledger instead of the user's project. When the state
    file itself is temp-isolated (as pytest and well-behaved harnesses arrange), temp
    roots are legitimate and kept."""
    return _in_system_temp(root) and not _in_system_temp(_global_state_path())


def remember_root(root: str) -> None:
    """Record the active root so the next launch — on any surface — defaults here
    instead of an empty ledger. Best-effort; never blocks startup. A temp-tree root is
    never recorded in the real config (``_leaked_temp_root``): an e2e ledger must not
    become the app's default project."""
    try:
        resolved = Path(root).expanduser().resolve()
        if _leaked_temp_root(resolved):
            return
        p = _global_state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"last_root": str(resolved)}, indent=2), encoding="utf-8")
    except OSError:
        pass


def recall_root() -> Optional[str]:
    """The last-used root, but only if it still holds a ledger and isn't a leaked
    temp-dir ledger (else ``None``)."""
    try:
        data = json.loads(_global_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    r = data.get("last_root")
    if not (r and has_ledger(r)):
        return None
    if _leaked_temp_root(Path(r)):    # a leftover e2e/test ledger, not the user's project
        return None
    return r


# ---- the one resolver -------------------------------------------------------
def resolve_root(explicit: Optional[str] = None) -> str:
    """Resolve the project root for ANY surface — see the module docstring for the
    precedence. ``explicit`` is the surface's ``--root`` (``None``/``"."`` means none)."""
    if explicit and explicit != ".":
        return str(Path(explicit).expanduser())
    env = os.environ.get("CITEVAHTI_ROOT")
    if env and env.strip():
        return str(Path(env).expanduser())
    if has_ledger("."):                       # a ledger in the cwd wins over history
        return str(Path(".").resolve())
    remembered = recall_root()                # chat and panel share this
    if remembered:
        return remembered
    return str(Path.home())                   # never bare cwd


def default_root() -> str:
    """The resolved root when no explicit ``--root`` is given (CLI/MCP default)."""
    return resolve_root(None)
