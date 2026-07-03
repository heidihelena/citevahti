"""Smoke-run a FROZEN CiteVahti artifact and prove it serves the review panel.

"The artifact built" is not "the artifact works": the 0.44.x release series shipped
three consecutive builds that froze/signed cleanly and then failed in a user's hands
(blank panel from missing package data, unsignable sidecar layout, mangled
Python.framework). This script is the missing gate — it RUNS the frozen binary the way
the product does and fails loudly if the panel wouldn't render:

  mcp mode (default)   spawn the stdio MCP server, do the MCP handshake, call the real
                       ``open_review_panel`` tool, then fetch the panel's core assets
                       over HTTP expecting 200s — the exact path Claude Desktop drives.
  engine mode          spawn the ``citevahti-engine`` sidecar with ``--root/--port``
                       (the CiteVahti.app window's server) and fetch the same assets.

Safety properties (learned 2026-07-02 the hard way):
  * an EPHEMERAL loopback port, never the product default — a developer's or CI
    machine may have a live CiteVahti instance on 8765 and this must never touch it;
  * a throwaway ``--root`` temp dir — no real ledger involved;
  * a hard watchdog — a hung binary fails the job instead of hanging it.

Stdlib only (runs on the bare CI runners, all three OSes).

Usage:
  python smoke_frozen_panel.py <binary> [--mode mcp|engine] [--timeout 120]
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

# The page skeleton plus the scripts whose absence has actually bitten: app.js (the app
# core), reconnect.js (the self-healing watchdog — must load before everything else),
# styles.css. index.html referencing a file NOT in this list is caught at test time by
# tests/test_panel_static_assets.py; this list is about the FROZEN artifact.
ASSETS = ("/index.html", "/app.js", "/styles.css", "/reconnect.js")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def arm_watchdog(proc: subprocess.Popen, seconds: float) -> threading.Timer:
    def _kill():
        print(f"WATCHDOG: binary still running after {seconds:.0f}s — killing", flush=True)
        proc.kill()
    t = threading.Timer(seconds, _kill)
    t.daemon = True
    t.start()
    return t


def fetch(url: str) -> tuple[int, int]:
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, len(r.read())


def check_assets(port: int) -> list[str]:
    failures = []
    try:
        status, _ = fetch(f"http://127.0.0.1:{port}/api/ping")
    except Exception as e:  # noqa: BLE001 — a missing liveness endpoint is the finding
        status = f"ERR ({e})"
    print(f"GET /api/ping -> {status}", flush=True)
    if status != 200:
        failures.append("/api/ping")
    for path in ASSETS:
        try:
            status, size = fetch(f"http://127.0.0.1:{port}{path}")
            ok = status == 200 and size > 0
        except Exception as e:  # noqa: BLE001 — any failure to serve is the finding
            status, size, ok = "ERR", 0, False
            print(f"GET {path} -> {e}", flush=True)
        print(f"GET {path} -> {status} ({size} bytes)", flush=True)
        if not ok:
            failures.append(path)
    return failures


def smoke_mcp(binary: str, timeout: float) -> list[str]:
    """Drive the frozen stdio MCP server through the REAL open_review_panel path."""
    root = tempfile.mkdtemp(prefix="cv-smoke-")
    port = free_port()
    proc = subprocess.Popen([binary, "--root", root], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    dog = arm_watchdog(proc, timeout)

    def send(msg: dict) -> None:
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def recv() -> dict:
        assert proc.stdout is not None
        while True:
            line = proc.stdout.readline()
            if not line:
                err = proc.stderr.read()[-2000:] if proc.stderr else ""
                raise RuntimeError(f"binary closed stdout; stderr tail: {err}")
            if line.strip():
                return json.loads(line)

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "clientInfo": {"name": "smoke", "version": "0"}}})
        recv()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "open_review_panel",
                         "arguments": {"port": port, "open_browser": False}}})
        payload = json.loads(recv()["result"]["content"][0]["text"])
        print(f"open_review_panel -> {payload.get('status')} at {payload.get('url')}", flush=True)
        if payload.get("status") not in ("started", "reused"):
            return [f"open_review_panel status={payload.get('status')}"]
        return check_assets(port)
    finally:
        dog.cancel()
        proc.kill()


def smoke_engine(binary: str, timeout: float) -> list[str]:
    """Spawn the engine sidecar the way the app shell does and fetch the panel."""
    root = tempfile.mkdtemp(prefix="cv-smoke-eng-")
    port = free_port()
    proc = subprocess.Popen([binary, "--root", root, "--port", str(port)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    dog = arm_watchdog(proc, timeout)
    try:
        deadline = time.monotonic() + min(60.0, timeout)
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read()[-2000:] if proc.stdout else ""
                return [f"engine exited rc={proc.returncode}; output tail: {out}"]
            try:
                if fetch(f"http://127.0.0.1:{port}/api/ping")[0] == 200:
                    break
            except Exception:  # noqa: BLE001 — not up yet
                time.sleep(0.5)
        else:
            return ["engine never answered /api/ping before the deadline"]
        return check_assets(port)
    finally:
        dog.cancel()
        proc.kill()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("binary", help="path to the frozen citevahti-mcp or citevahti-engine")
    ap.add_argument("--mode", choices=("mcp", "engine"), default="mcp")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="hard watchdog: kill the binary and fail after this many seconds")
    args = ap.parse_args(argv)

    failures = (smoke_mcp if args.mode == "mcp" else smoke_engine)(args.binary, args.timeout)
    if failures:
        print(f"PANEL SMOKE FAILED ({args.mode}): {failures}", flush=True)
        return 1
    print(f"PANEL SMOKE PASSED ({args.mode}) — the frozen artifact serves the panel", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
