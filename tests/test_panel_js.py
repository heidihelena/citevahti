"""Run the headless JS navigation test (tests/panel_js/nav_test.js) under pytest.

The inliner's claim-activation/navigation logic lives in panel/web/app.js; this
guards it (document-order j/k + auto-advance, no stranded claims) without a browser.
Skips cleanly when Node isn't installed, so the Python-only path still passes."""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
SCRIPT = Path(__file__).parent / "panel_js" / "nav_test.js"


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_inliner_navigation_js():
    result = subprocess.run([NODE, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
