"""One rotating log file per shell/sidecar component, all under ``paths.log_dir()``.

Shared by the shell (``app.log``), the engine (``engine.log``), and the MCP sidecar
(``mcp.log``) — never the panel/CLI surfaces, which have their own human-facing stdout/
stderr conventions. Best-effort directory creation, matching ``rootcfg.remember_root``'s
"never blocks startup" convention.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from . import paths

_MAX_BYTES = 5_000_000
_BACKUP_COUNT = 3


def get_logger(name: str) -> logging.Logger:
    """A ``logging.Logger`` named ``name`` writing to ``<log_dir>/<name>.log``.

    Idempotent: calling this twice for the same ``name`` returns the same logger without
    attaching a second handler (rotation would otherwise be split across duplicate writes).
    """
    logger = logging.getLogger(f"citevahti.{name}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        log_dir = paths.log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / f"{name}.log", maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger
