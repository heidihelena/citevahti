"""Build a small, fully synthetic CiteVahti ledger for screenshots and demos.

Thin wrapper around the shipped builder (``citevahti.demo``) so the screenshot
tooling and the user-facing ``citevahti demo`` command share ONE source of truth.

Usage:
    PYTHONPATH=src python3 docs/demo/build_demo_ledger.py [OUTPUT_ROOT]

Then point the panel at it:
    PYTHONPATH=src python3 -m citevahti.panel.server --root OUTPUT_ROOT --port 8775
"""

from __future__ import annotations

import sys
from pathlib import Path

from citevahti.demo import build

if __name__ == "__main__":
    out = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path(".demo-ledger")
    summary = build(out)
    print(f"Demo ledger built at {summary['root']}")
    print(f"  manuscript: {summary['manuscript']}")
    print(f"  claims:     {summary['claims']} ({summary['decided']} decided, "
          f"{summary['pending']} pending)")
