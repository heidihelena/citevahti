"""Run the panel's JavaScript behaviour suite (``frontend-tests/``) under pytest.

The unit / component / error / a11y tests run on ``node:test`` + jsdom; they need the dev
deps installed once (``cd frontend-tests && npm install``). This skips cleanly when node or
the deps are absent, so the Python-only path still passes.

The Playwright e2e suite needs a browser and starts the panel server, so it is opt-in via
``CITEVAHTI_E2E=1`` (and a demo ledger at ``.demo-ledger`` — regenerate with
``docs/demo/build_demo_ledger.py``)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

FT = Path(__file__).resolve().parent.parent / "frontend-tests"
NODE = shutil.which("node")
NPM = shutil.which("npm")
HAVE_DEPS = (FT / "node_modules").is_dir()


@pytest.mark.skipif(NODE is None or NPM is None, reason="node/npm not available")
@pytest.mark.skipif(not HAVE_DEPS, reason="run `cd frontend-tests && npm install` first")
def test_panel_js_behaviour_suite():
    """Unit + component + error + accessibility behaviour (node:test + jsdom)."""
    r = subprocess.run([NPM, "test"], cwd=FT, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(os.environ.get("CITEVAHTI_E2E") != "1", reason="e2e is opt-in (set CITEVAHTI_E2E=1)")
@pytest.mark.skipif(not HAVE_DEPS, reason="run `cd frontend-tests && npm install` first")
def test_panel_e2e_full_flow():
    """Full user flow + interactive a11y in a real browser (Playwright)."""
    r = subprocess.run([NPM, "run", "e2e"], cwd=FT, capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stdout + r.stderr
