#!/usr/bin/env python3
"""Record a short screen-capture of the CiteVahti demo for social/community posts.

Drives the real panel through Rate → Reveal → Decide on the bundled `citevahti demo`
ledger, with an on-screen caption and a glowing cursor so a silent clip is readable.
Records to webm via Playwright, then transcodes to mp4 (+ gif) using Playwright's
bundled ffmpeg — no system ffmpeg needed.

    pip install playwright && playwright install chromium
    PYTHONPATH=src python3 docs/demo/record_demo.py            # -> ~/Downloads/citevahti-demo.{mp4,gif}

Fully synthetic (the `citevahti demo` ledger) and run with an isolated HOME, so the
clip never shows real ledgers, names, or paths — safe to publish.
"""

from __future__ import annotations

import argparse
import os
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
VIEWPORT = {"width": 1280, "height": 800}

HELPERS = r"""
window.__demo = {
  cap(text){let c=document.getElementById('__cap');
    if(!c){c=document.createElement('div');c.id='__cap';
      c.style.cssText='position:fixed;left:0;right:0;bottom:0;z-index:99999;color:#fff;'
       +'font:600 24px/1.4 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;padding:46px 30px 24px;'
       +'text-align:center;background:linear-gradient(transparent,rgba(20,14,38,.92));opacity:0;transition:opacity .35s';
      document.body.appendChild(c);}
    c.textContent=text;requestAnimationFrame(()=>c.style.opacity='1');},
  cur(){let d=document.getElementById('__cur');
    if(!d){d=document.createElement('div');d.id='__cur';
      d.style.cssText='position:fixed;left:50%;top:46%;width:24px;height:24px;border-radius:50%;'
       +'background:rgba(139,111,201,.45);border:2.5px solid #6B4E9E;z-index:100000;pointer-events:none;'
       +'transform:translate(-50%,-50%);transition:left .55s ease,top .55s ease,transform .12s;'
       +'box-shadow:0 0 14px rgba(139,111,201,.6)';
      document.body.appendChild(d);}return d;},
  move(sel){const el=document.querySelector(sel);if(!el)return false;const r=el.getBoundingClientRect();
    const d=this.cur();d.style.left=(r.left+r.width/2)+'px';d.style.top=(r.top+r.height/2)+'px';return true;},
  tap(){const d=this.cur();d.style.transform='translate(-50%,-50%) scale(.65)';
    setTimeout(()=>{d.style.transform='translate(-50%,-50%) scale(1)';},130);}
};
"""


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_panel(root: Path, port: int, home: Path) -> subprocess.Popen:
    home.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(SRC), "HOME": str(home),
           "USERPROFILE": str(home), "XDG_CONFIG_HOME": str(home / ".config")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "citevahti.panel.server", "--root", str(root), "--port", str(port)],
        env=env, cwd=str(home), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{base}/api/context", timeout=0.5)
            return proc
        except Exception:  # noqa: BLE001
            if proc.poll() is not None:
                raise SystemExit(f"panel exited early (code {proc.returncode})")
            time.sleep(0.1)
    proc.terminate()
    raise SystemExit("panel did not come up on time")


def _rate_claim(root: Path) -> str | None:
    """The demo claim staged for a blind rating (AI in, no human yet)."""
    from citevahti.state import CiteVahtiStore
    store = CiteVahtiStore(root)
    for cid in store.list_claims():
        c = store.load_claim(cid)
        if c.claim_text.startswith("A single patient leaflet"):
            return cid
    return None


def _full_ffmpeg() -> str | None:
    """A full ffmpeg (for mp4/gif) — system first, else the one imageio-ffmpeg ships.
    NOT Playwright's bundled ffmpeg, which is a stripped recorder build with no encoders."""
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path.home() / "Downloads"),
                    help="output directory (default ~/Downloads)")
    args = ap.parse_args()
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright not installed — pip install playwright && playwright install chromium")

    from citevahti.demo import build

    tmp = Path(tempfile.mkdtemp(prefix="cv-rec-"))
    demo, home, viddir = tmp / "demo", tmp / "home", tmp / "vid"
    build(demo)
    claim = _rate_claim(demo)
    proc = _start_panel(demo, _free_port(), home)
    port = int(proc.args[proc.args.index("--port") + 1])
    base = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport=VIEWPORT,
                                      record_video_dir=str(viddir), record_video_size=VIEWPORT)
            page = ctx.new_page()
            focus = f"&focus={claim}" if claim else ""
            page.goto(f"{base}/?theme=light{focus}", wait_until="networkidle")
            page.wait_for_selector(".stepper", timeout=8000)
            page.add_script_tag(content=HELPERS)

            def cap(t):
                page.evaluate(f"__demo.cap({t!r})")

            def click(sel, hold=1200):
                page.evaluate(f"__demo.move({sel!r})")
                page.wait_for_timeout(650)
                page.evaluate("__demo.tap()")
                page.click(sel)
                page.wait_for_timeout(hold)

            cap("Does the cited paper actually support the claim?")
            page.wait_for_timeout(2400)
            cap("You rate the support yourself — the AI stays blinded.")
            page.wait_for_timeout(1500)
            click('[data-rate="partially_supports"]', hold=1500)
            cap("Now the AI's blinded second opinion is revealed.")
            page.wait_for_timeout(2200)
            try:
                page.wait_for_selector("[data-decide]", timeout=4000)
                cap("You decide — it's recorded with an audit trail.")
                page.wait_for_timeout(1300)
                click('[data-decide="accepted_with_caution"]', hold=1700)
            except Exception:  # noqa: BLE001
                cap("You decide — it's recorded with an audit trail.")
                page.wait_for_timeout(1800)
            cap("Free · local-first · github.com/heidihelena/citevahti")
            page.wait_for_timeout(2600)
            page.evaluate("document.getElementById('__cur')?.remove()")
            page.wait_for_timeout(300)
            ctx.close()                       # finalizes the webm
            browser.close()

        webm = next(viddir.glob("*.webm"))
        dest_webm = out / "citevahti-demo.webm"
        shutil.copy(webm, dest_webm)          # always keep the playable source
        print(f"wrote {dest_webm}")

        # A full ffmpeg can also produce mp4 + gif (Playwright's bundled one can't encode).
        ff = _full_ffmpeg()
        if not ff:
            print("(for mp4 + gif: `pip install imageio-ffmpeg` (or brew install ffmpeg), then re-run)")
            return
        mp4, gif = out / "citevahti-demo.mp4", out / "citevahti-demo.gif"
        try:
            subprocess.run([ff, "-y", "-i", str(webm), "-vf",
                            "scale=1080:-2,format=yuv420p", "-movflags", "+faststart",
                            "-an", str(mp4)], check=True, capture_output=True)
            subprocess.run([ff, "-y", "-i", str(webm), "-vf",
                            "fps=12,scale=720:-1:flags=lanczos", str(gif)],
                           check=True, capture_output=True)
            print(f"wrote {mp4}\nwrote {gif}")
        except subprocess.CalledProcessError as exc:
            print(f"(ffmpeg transcode failed: {exc.stderr.decode()[:160]}; the .webm is fine)")
    finally:
        proc.terminate()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
