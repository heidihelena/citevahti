"""``citevahti start`` — one command brings up the whole v1 workflow (ADR-0007).

The two co-primary surfaces normally take three manual steps: register the MCP
server in a chat client, launch the loopback panel, and open a browser. This
collapses them into a single command that is *also* the one line you put in your
chat client's MCP config:

    "command": "citevahti", "args": ["start", "--root", "/path/to/project"]

When the client spawns it, ``start`` side-launches the loopback panel + browser in
a background thread and then serves the MCP tools over stdio in the foreground. A
human can also run it in a terminal just to bring the panel up.

Two hard rules live here:

  * **stdout is the MCP protocol channel.** Every human-facing line goes to
    *stderr* (``_say``); we never print guidance to stdout, or we'd corrupt the
    stdio MCP stream the chat client reads.
  * **the panel stays loopback.** ``start`` only ever binds ``127.0.0.1``; the
    non-loopback escape hatch lives in ``citevahti-panel``, not here.
"""

from __future__ import annotations

import sys
import threading
import webbrowser
from typing import Callable, Optional

from .probe import HttpxClient, run_probes
from .state import CiteVahtiStore


# ---- readiness ---------------------------------------------------------------
def preflight_snapshot(root: str, client=None) -> dict:
    """A read-only snapshot of project + backend readiness.

    Never raises on a missing project or an unreachable backend — every field
    degrades to a safe default. Shared by ``citevahti preflight`` (as JSON) and by
    ``start`` (rendered into plain next-step prompts).
    """
    store = CiteVahtiStore(root)
    initialized = store.exists()
    out: dict = {
        "project_initialized": initialized,
        "project_dir": str(store.dir),
        "zotero": {"reachable": False, "version": None},
        "better_bibtex": {"reachable": False, "version": None},
        "zotero_write_ready": False,
        "claims": None,
    }
    try:
        report = run_probes(client or HttpxClient())
        z = report.results.get("zotero_api")
        if z is not None:
            out["zotero"] = {"reachable": bool(z.available), "version": z.version}
        b = report.results.get("bbt_ready")
        if b is not None:
            out["better_bibtex"] = {"reachable": bool(b.available), "version": b.version}
    except Exception:
        pass
    if initialized:
        try:
            from .report import ClaimReportService
            rep = ClaimReportService(store).report()
            out["claims"] = {
                "total": rep.total,
                "verified": rep.counts.get("verified", 0),
                "needs_support": rep.counts.get("needs_support", 0),
                "review_needed": rep.counts.get("review_needed", 0),
                "decision_recorded": rep.counts.get("decision_recorded", 0),
                "with_candidates": sum(1 for r in rep.rows if r.candidate_count > 0),
            }
        except Exception:
            pass
        try:
            from .capabilities import CapabilityStatusService
            crep = CapabilityStatusService(store, client or HttpxClient()).report()
            out["zotero_write_ready"] = bool(crep.write_backend_available)
        except Exception:
            pass
    return out


def readiness_lines(snapshot: dict) -> list[str]:
    """Turn a preflight snapshot into plain next-step prompts for the human.

    Deliberately humane and imperative ("Open Zotero", "Choose a manuscript") —
    the PhD-student ask is to be told what to do next, not handed a status table.
    """
    lines: list[str] = []
    if not snapshot.get("project_initialized"):
        lines.append(f"This folder has no ledger yet → run  citevahti init  "
                     f"(creates {snapshot.get('project_dir')}).")
    if not snapshot.get("zotero", {}).get("reachable"):
        lines.append("Open Zotero so writes can be previewed and added back "
                     "(it answers on localhost:23119).")
    elif not snapshot.get("better_bibtex", {}).get("reachable"):
        lines.append("Zotero is up, but the Better BibTeX add-on isn't detected — "
                     "install it for citekeys and bibliography export.")
    elif not snapshot.get("zotero_write_ready"):
        lines.append("Zotero is up but not write-ready yet — run  citevahti status  "
                     "to see what's missing before you cite.")

    claims = snapshot.get("claims")
    if snapshot.get("project_initialized"):
        if not claims or claims.get("total", 0) == 0:
            lines.append("Choose a manuscript: in the chat, run the "
                         "run_claim_tests prompt and paste a paragraph to begin.")
        else:
            need = claims.get("needs_support", 0) + claims.get("review_needed", 0)
            tail = (f"{need} still need your rating — review them in the panel."
                    if need else "all rated; record decisions in the panel to cite.")
            lines.append(f"{claims['total']} claims recorded; {tail}")
    if not lines:
        lines.append("Everything looks ready — rate in the panel, cite from there.")
    return lines


# ---- orchestration -----------------------------------------------------------
def is_citevahti_panel(url: str, *, timeout: float = 1.0) -> bool:
    """True iff ``url`` answers ``/api/health`` like a CiteVahti panel.

    Used to tell "a CiteVahti panel is already open on this port" (safe to reuse)
    apart from "some unrelated service has the port" (we must not pretend it's a
    rating surface). The fingerprint is the health body's shape, which only the
    panel's ``/api/health`` (``agent.tools.status``) produces.
    """
    import httpx
    try:
        resp = httpx.get(f"{url}/api/health", timeout=timeout)
        if resp.status_code != 200:
            return False
        body = resp.json()
    except Exception:
        return False
    return isinstance(body, dict) and "write_backend" in body and "connections" in body


def _default_mcp_runner(root: str) -> int:
    """Build and serve the constrained MCP tools over stdio (blocks).

    Raises ``RuntimeError`` (with install guidance) if the ``mcp`` extra is absent.
    """
    from .agent import mcp_server
    mcp_server.build_server(root=root).run()
    return 0


def start(
    root: str = ".",
    *,
    port: int = 8765,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    client=None,
    mcp_runner: Optional[Callable[[str], int]] = None,
    browser_opener: Optional[Callable[[str], object]] = None,
    panel_probe: Optional[Callable[[str], bool]] = None,
    out=None,
) -> int:
    """Launch panel (background thread) + browser, then serve MCP in the foreground.

    All side effects are injectable so the orchestration is testable without
    binding a real MCP stdio stream or popping a browser:
      * ``mcp_runner(root)`` — defaults to the stdio MCP server (blocking).
      * ``browser_opener(url)`` — defaults to :func:`webbrowser.open`.
      * ``panel_probe(url)`` — defaults to :func:`is_citevahti_panel`; decides
        whether a busy port is already a CiteVahti panel.
      * ``out`` — where guidance is written; defaults to ``sys.stderr`` because
        stdout belongs to the MCP protocol.
    """
    from .panel.server import is_loopback, make_server

    out = out if out is not None else sys.stderr
    browser_opener = browser_opener or webbrowser.open
    mcp_runner = mcp_runner or _default_mcp_runner
    panel_probe = panel_probe or is_citevahti_panel

    def _say(msg: str = "") -> None:
        print(msg, file=out, flush=True)

    # Loopback is a safety invariant, not just a default: the panel has no auth and
    # renders manuscript claims/evidence. Enforce it here too, not only in
    # ``citevahti-panel`` (defense in depth — the CLI never offers ``--host``).
    if not is_loopback(host):
        _say(f"refusing to bind {host!r}: 'citevahti start' is loopback-only "
             "(the panel has no auth). Use 127.0.0.1.")
        return 2

    _say("CiteVahti — starting your review workspace.")
    for line in readiness_lines(preflight_snapshot(root, client)):
        _say(f"  • {line}")

    # The loopback panel (the blind human decision surface) in a daemon thread.
    url = f"http://{host}:{port}"
    httpd = None
    try:
        httpd = make_server(root, host, port)
    except OSError:
        # Port busy: only reuse it if it is *actually* a CiteVahti panel. A foreign
        # occupant must fail loudly — never leave the human thinking they have a
        # rating surface when they don't.
        if panel_probe(url):
            _say(f"\nPanel: a CiteVahti panel is already open at {url} — reusing it.")
            if open_browser:
                try:
                    browser_opener(url)
                except Exception:
                    _say(f"  (couldn't open a browser automatically — visit {url}.)")
        else:
            _say(f"\nPort {port} is busy and is not a CiteVahti panel. Free it, or "
                 f"pick another port with --port. Not starting (no rating surface).")
            return 2
    if httpd is not None:
        thread = threading.Thread(target=httpd.serve_forever, name="citevahti-panel",
                                  daemon=True)
        thread.start()
        _say(f"\nPanel ready → {url}  (loopback only; rate here before the AI shows).")
        if open_browser:
            try:
                browser_opener(url)
            except Exception:
                _say(f"  (couldn't open a browser automatically — visit {url}.)")

    try:
        return _serve_foreground(root, httpd, url, mcp_runner, _say)
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()


def _block_until_interrupt() -> None:
    """Park the foreground thread until Ctrl-C (panel keeps serving in the
    background). Factored out so tests can drive the interrupt deterministically."""
    threading.Event().wait()


def _serve_foreground(root, httpd, url, mcp_runner, say) -> int:
    """Serve MCP over stdio in the foreground; fall back to the panel if the MCP
    extra is missing, so ``start`` still leaves the human a working surface."""
    say("\nServing the MCP tools (stdio) — connect your chat client. Ctrl-C to stop.")
    try:
        return mcp_runner(root)
    except RuntimeError as exc:
        say(f"\nMCP server unavailable: {exc}")
        if httpd is None:
            return 1
        say(f"Keeping the panel up at {url}. Ctrl-C to stop.")
        try:
            _block_until_interrupt()      # panel keeps serving in the background
        except KeyboardInterrupt:
            pass
        return 0
    except KeyboardInterrupt:
        say("\nstopped.")
        return 0
