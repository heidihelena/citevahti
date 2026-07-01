"""PyInstaller entry point for the ``citevahti-engine`` sidecar.

Frozen alongside the shell (``pyi_app_entry.py``) into the same ``CiteVahti.app`` bundle by
build-app.sh — a second executable at ``Contents/MacOS/citevahti-engine`` that the shell
spawns and supervises, not a second top-level app.
"""

import sys

from citevahti.engine import main

if __name__ == "__main__":
    sys.exit(main())
