"""Where the project ledger (``.citevahti/``) lives — resolved to a STABLE location.

Single-user and local-first: when no ``--root`` is given the default must NOT be the
process working directory. The CLI is run from wherever the user happens to be, but the
MCP server is launched by the desktop app with an arbitrary cwd (often ``/``) — so a
cwd-relative default makes ``citevahti init`` (run from home) and the desktop-launched
``mcp-serve`` look at different places and report "no config" on the same machine.

The default is therefore ``$CITEVAHTI_ROOT`` if set, else the user's **home** directory
(so the ledger is ``~/.citevahti``). Pass ``--root`` for a per-project ledger.
"""

from __future__ import annotations

import os
from pathlib import Path


def default_root() -> str:
    """The stable default project root: ``$CITEVAHTI_ROOT`` else the home directory."""
    env = os.environ.get("CITEVAHTI_ROOT")
    if env and env.strip():
        return str(Path(env).expanduser())
    return str(Path.home())
