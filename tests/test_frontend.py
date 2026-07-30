"""Run the panel's JavaScript behaviour suite (``frontend-tests/``) under pytest.

The unit / component / error / a11y tests run on ``node:test`` + jsdom; they need the dev
deps installed once (``cd frontend-tests && npm install``). Locally this skips cleanly when
node or the deps are absent, so the Python-only path still passes. **In CI (the ``CI`` env
var is set) a missing node or ``node_modules`` FAILS instead of skipping** — a silent skip
let a green run say nothing about the panel; the dedicated ``frontend`` CI job installs the
deps and runs this file.

The Playwright e2e suite needs a browser and starts the panel server, so it is opt-in via
``CITEVAHTI_E2E=1`` (and a demo ledger at ``.demo-ledger`` — regenerate with
``docs/demo/build_demo_ledger.py``). The ``frontend`` CI job sets it."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

FT = Path(__file__).resolve().parent.parent / "frontend-tests"
NODE = shutil.which("node")
NPM = shutil.which("npm")
HAVE_DEPS = (FT / "node_modules").is_dir()
IN_CI = bool(os.environ.get("CI"))


def _require_node_and_deps() -> None:
    """Skip locally when the JS toolchain is absent; fail loudly in CI.

    In CI a skip here would turn the run green without executing a single panel
    test — that is a broken gate, not an optional suite.
    """
    missing = None
    if NODE is None or NPM is None:
        missing = "node/npm not on PATH"
    elif not HAVE_DEPS:
        missing = "frontend-tests/node_modules missing (cd frontend-tests && npm ci)"
    if missing is None:
        return
    if IN_CI:
        pytest.fail(
            f"{missing} — CI must install the frontend toolchain before pytest; "
            "skipping here would make CI green without running the panel suite"
        )
    pytest.skip(missing)


def test_panel_js_behaviour_suite():
    """Unit + component + error + accessibility behaviour (node:test + jsdom)."""
    _require_node_and_deps()
    r = subprocess.run([NPM, "test"], cwd=FT, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(os.environ.get("CITEVAHTI_E2E") != "1", reason="e2e is opt-in (set CITEVAHTI_E2E=1)")
def test_panel_e2e_full_flow():
    """Full user flow + interactive a11y in a real browser (Playwright)."""
    _require_node_and_deps()
    r = subprocess.run([NPM, "run", "e2e"], cwd=FT, capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stdout + r.stderr
