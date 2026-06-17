#!/usr/bin/env python3
"""Regenerate the README screenshots from the synthetic demo ledger — in LIGHT mode.

The panel defaults to dark, and the theme is toggled per-browser; this script forces
light with the `?theme=light` URL hook (see app.js → applyTheme) so the captures are
deterministic and match the README, which is written light.

Needs a browser, which the panel itself does not — so this is a dev/release tool, not
part of the test suite:

    pip install playwright
    playwright install chromium
    PYTHONPATH=src python3 docs/demo/capture_screenshots.py

Writes 01-review-surface, 02-legend, 03-first-run, 04-rate-reveal-decide-write,
06-ai-settings, and 07-report-export PNGs into docs/screenshots/.
Captured at device_scale_factor=3 to roughly match the existing retina PNGs. Target a
specific claim card with `--focus <claim_id>` (otherwise the first claim is opened).
"""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
OUT = REPO / "docs" / "screenshots"
VIEWPORT = {"width": 1280, "height": 832}
SCALE = 3


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run(cmd: list[str], **kw) -> None:
    env = {**kw.pop("env", {}), "PYTHONPATH": str(SRC)}
    import os
    subprocess.run(cmd, check=True, env={**os.environ, **env}, **kw)


def _build_ledger(root: Path, *, empty: bool) -> None:
    """A full demo ledger (claims + decisions) or an init-only empty one (first run)."""
    root.mkdir(parents=True, exist_ok=True)
    if empty:
        # --root is a global flag (before the subcommand): `citevahti --root X init`
        _run([sys.executable, "-m", "citevahti.cli", "--root", str(root), "init"])
    else:
        _run([sys.executable, str(REPO / "docs" / "demo" / "build_demo_ledger.py"), str(root)])


def _rate_phase_claim(root: Path) -> str | None:
    """The demo claim left awaiting a human rating (candidate + AI rating staged, no
    human verdict) — opening it shows the blind Rate card, the centrepiece of shot 1."""
    from citevahti.state import CiteVahtiStore
    store = CiteVahtiStore(root)
    for cid in store.list_claims():
        c = store.load_claim(cid)
        if c.claim_text.startswith("A single patient leaflet") and store.candidates_exist(cid):
            return cid
    return None


def _decided_claim(root: Path) -> str | None:
    """A demo claim carried all the way to a recorded verdict — opening it shows the
    stepper with Rate/Reveal/Decide complete (shot 4, the core interaction)."""
    from citevahti.state import CiteVahtiStore
    store = CiteVahtiStore(root)
    decided = {d.replace("dec-", "") for d in store.list_decisions()}
    for cid in store.list_claims():
        if store.candidates_exist(cid):
            if any(c.candidate_id in decided for c in store.load_candidates(cid).candidates):
                return cid
    return None


def _start_panel(root: Path, port: int) -> subprocess.Popen:
    import os
    proc = subprocess.Popen(
        [sys.executable, "-m", "citevahti.panel.server", "--root", str(root), "--port", str(port)],
        env={**os.environ, "PYTHONPATH": str(SRC)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):  # ~10s
        try:
            urllib.request.urlopen(f"{base}/api/context", timeout=0.5)
            return proc
        except Exception:  # noqa: BLE001
            if proc.poll() is not None:
                raise SystemExit(f"panel exited early (code {proc.returncode})")
            time.sleep(0.1)
    proc.terminate()
    raise SystemExit("panel did not come up on time")


def _shoot(page, url: str, ready_selector: str, dest: Path, *, click_first_claim: bool = False,
           focus: str | None = None) -> None:
    page.goto(url, wait_until="networkidle")
    if focus is None and click_first_claim:
        page.wait_for_selector(".claim", timeout=5000)
        page.click(".claim")
    page.wait_for_selector(ready_selector, timeout=5000)
    page.wait_for_timeout(400)  # let highlight transitions settle
    page.screenshot(path=str(dest))
    print(f"wrote {dest}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--focus", default=None, help="claim_id to open for the review-surface shot")
    ap.add_argument("--out", default=str(OUT), help="output directory (default docs/screenshots)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright not installed — run: pip install playwright && playwright install chromium")

    tmp = Path(tempfile.mkdtemp(prefix="cv-shots-"))
    demo, empty = tmp / "demo", tmp / "empty"
    procs: list[subprocess.Popen] = []
    try:
        _build_ledger(demo, empty=False)
        _build_ledger(empty, empty=True)
        demo_port, empty_port = _free_port(), _free_port()
        procs += [_start_panel(demo, demo_port), _start_panel(empty, empty_port)]
        demo_base, empty_base = f"http://127.0.0.1:{demo_port}", f"http://127.0.0.1:{empty_port}"
        focus = args.focus or _rate_phase_claim(demo)
        focus_q = f"&focus={focus}" if focus else ""

        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE)
            page = ctx.new_page()
            # 1. review surface — the blind Rate card open over the manuscript, light mode
            _shoot(page, f"{demo_base}/?theme=light{focus_q}", ".stepper",
                   out / "01-review-surface.png", click_first_claim=not focus, focus=focus)
            # 2. the verdict legend, open over the manuscript
            _shoot(page, f"{demo_base}/?theme=light&legend=1", "#legend:not([hidden])",
                   out / "02-legend.png")
            # 3. first run on an empty ledger — the paste-a-manuscript box
            _shoot(page, f"{empty_base}/?theme=light", "textarea",
                   out / "03-first-run.png")
            # 4. the Rate → Reveal → Decide → Write stepper — the right-hand card,
            #    cropped, on a claim carried to a verdict (the core interaction)
            decided = _decided_claim(demo)
            decided_q = f"&focus={decided}" if decided else ""
            page.goto(f"{demo_base}/?theme=light{decided_q}", wait_until="networkidle")
            if not decided:
                page.wait_for_selector(".claim", timeout=5000); page.click(".claim")
            page.wait_for_selector(".stepper", timeout=5000)
            page.wait_for_timeout(400)
            page.locator("#card").screenshot(path=str(out / "04-rate-reveal-decide-write.png"))
            print(f"wrote {out / '04-rate-reveal-decide-write.png'}")
            # 6. AI second-opinion settings — Off / Local AI / My API key
            page.goto(f"{demo_base}/?theme=light", wait_until="networkidle")
            page.click("#aiSettings")
            page.wait_for_selector("#aiModal .modal-card", timeout=5000)
            page.wait_for_timeout(400)
            page.locator("#aiModal .modal-card").screenshot(path=str(out / "06-ai-settings.png"))
            print(f"wrote {out / '06-ai-settings.png'}")
            # 7. the citation-integrity report export
            page.goto(f"{demo_base}/?theme=light", wait_until="networkidle")
            page.click("#report")
            page.wait_for_selector("#exportModal .modal-card", timeout=5000)
            page.wait_for_timeout(400)
            page.locator("#exportModal .modal-card").screenshot(path=str(out / "07-report-export.png"))
            print(f"wrote {out / '07-report-export.png'}")
            browser.close()
    finally:
        for proc in procs:
            proc.terminate()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
