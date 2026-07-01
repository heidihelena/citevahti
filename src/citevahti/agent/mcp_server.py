"""MCP server exposing ONLY the constrained CiteVahti agent surface.

The protocol layer is intentionally thin: it registers exactly ``agent.TOOLS``
(re-checked against the policy allow-list) and nothing else. All safety lives in
the engine + the tool wrappers. ``mcp`` is an optional dependency — importing
this module is cheap; the SDK is only needed to actually serve.
"""

from __future__ import annotations

from . import TOOLS, assert_safe_surface
from .prompts import (
    CHECK_PARAGRAPH_PROMPT_DESCRIPTION,
    CHECK_PARAGRAPH_PROMPT_NAME,
    CLAIM_TEST_PROMPT_DESCRIPTION,
    CLAIM_TEST_PROMPT_NAME,
    METHODS_PROMPT_DESCRIPTION,
    METHODS_PROMPT_NAME,
    REVIEW_PROMPT_DESCRIPTION,
    REVIEW_PROMPT_NAME,
    SCREEN_TOPIC_PROMPT_DESCRIPTION,
    SCREEN_TOPIC_PROMPT_NAME,
    check_paragraph_prompt,
    methods_prompt,
    run_claim_tests_prompt,
    screen_topic_prompt,
)


def build_server(name: str = "citevahti", *, root: str = ".", host: str = "127.0.0.1",
                  port: int = 8766):
    """Build a FastMCP server with the constrained tools bound to ``root``.

    ``host``/``port`` only matter for the ``streamable-http`` transport (the ``stdio``
    transport used by the Claude Desktop ``.mcpb`` ignores them) — ``host`` is never
    surfaced as a flag on ``main()``, always ``127.0.0.1``, the same loopback-only
    invariant enforced elsewhere in CiteVahti.

    Raises a clear error if the ``mcp`` package isn't installed.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "the 'mcp' package is required to serve (pip install 'citevahti[mcp]')") from exc

    assert_safe_surface(TOOLS.keys())          # defense in depth at serve time
    server = FastMCP(name, host=host, port=port)

    # A plain identity/liveness check for the desktop app's supervisor (SidecarSupervisor)
    # to confirm — over streamable-http only — that a given port really is *this* project's
    # CiteVahti MCP sidecar, not merely something else that happens to answer on it.
    @server.custom_route("/health", methods=["GET"])
    async def _health(request):  # pragma: no cover — exercised via the streamable-http app
        from starlette.responses import JSONResponse

        from .. import __version__
        return JSONResponse({
            "ok": True, "service": "citevahti-mcp", "root": root, "version": __version__,
        })

    # The user-controlled prompt that choreographs the blinded claim-test loop. It
    # adds NO new capability — it only instructs the chat LLM in how to drive the
    # existing tools while keeping the blind (human rates first) and gating writes.
    @server.prompt(name=CLAIM_TEST_PROMPT_NAME, description=CLAIM_TEST_PROMPT_DESCRIPTION)
    def run_claim_tests(manuscript: str = "") -> str:
        return run_claim_tests_prompt(manuscript)

    # Layer-0 topic screening (ADR-0008): propose candidate claims + nearby evidence for a
    # topic (leads, not verdicts), then hand off to run_claim_tests. Same blinded contract.
    @server.prompt(name=SCREEN_TOPIC_PROMPT_NAME, description=SCREEN_TOPIC_PROMPT_DESCRIPTION)
    def screen_topic(topic: str = "") -> str:
        return screen_topic_prompt(topic)

    # Everyday in-writing check: a read-only lookup of a drafted paragraph against the
    # ledger, then hand off to run_claim_tests. Adds NO capability; rates/decides nothing.
    @server.prompt(name=CHECK_PARAGRAPH_PROMPT_NAME, description=CHECK_PARAGRAPH_PROMPT_DESCRIPTION)
    def check_paragraph(paragraph: str = "") -> str:
        return check_paragraph_prompt(paragraph)

    # Read-only methods text: the workflow paragraph + PRISMA AI-disclosure + flow counts,
    # for a methods section / systematic review. Reports + discloses; judges nothing.
    @server.prompt(name=METHODS_PROMPT_NAME, description=METHODS_PROMPT_DESCRIPTION)
    def methods_statement() -> str:
        return methods_prompt()

    # Deprecated alias kept for clients that connected via 0.9.0 (same workflow).
    @server.prompt(name=REVIEW_PROMPT_NAME, description=REVIEW_PROMPT_DESCRIPTION)
    def review_manuscript(manuscript: str = "") -> str:
        return run_claim_tests_prompt(manuscript)

    def _bind(fn):
        import functools
        import inspect
        import typing

        sig = inspect.signature(fn)
        hints = typing.get_type_hints(fn)
        exposed = [
            param.replace(annotation=hints.get(param.name, param.annotation))
            for param in sig.parameters.values()
            if param.name != "root"
        ]

        @functools.wraps(fn)
        def tool(**kwargs):
            return fn(root=root, **kwargs)

        # FastMCP builds JSON schemas from the callable signature. The wrapper
        # itself is **kwargs, but the MCP client must see the real tool inputs
        # with the server-bound project root hidden.
        tool.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
            parameters=exposed,
            return_annotation=hints.get("return", sig.return_annotation),
        )
        return tool

    for tool_name, fn in TOOLS.items():
        server.tool(name=tool_name)(_bind(fn))
    return server


def _pick_loopback_port(preferred: int) -> int:
    """Try ``preferred`` first; fall back to an OS-assigned loopback port if it's taken.

    Always reads back the real bound port via ``getsockname()`` rather than assuming
    success means "the preferred port" — ``preferred=0`` is itself a valid "any free port"
    request, and a bare ``return preferred`` would wrongly hand back ``0`` instead of the
    port the OS actually assigned.

    A brief bind-then-release probe (not a held socket) — the same small TOCTOU window
    every "pick a free port" helper has, acceptable here since the only thing racing for
    this port is this single local user's own previous CiteVahti MCP process.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", preferred))
        except OSError:
            probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _serve_streamable_http(root: str, preferred_port: int,
                           parent_pid: "int | None" = None) -> int:
    """The desktop app's agent-server sidecar path: loopback ``streamable-http``, with the
    same runtime-file handshake + rotating log the ``citevahti-engine`` sidecar uses.

    FastMCP's ``run(transport="streamable-http")`` doesn't hand back the internal uvicorn
    server, so there's no handle to ask for a graceful in-flight-request drain on
    ``SIGTERM``/``SIGINT`` — this does a clean-enough shutdown instead (clear the runtime
    handshake file, then exit immediately), which is the guarantee that actually matters
    for a single local user's own agent sidecar with no other clients' connections to
    protect.
    """
    import os
    import signal
    from datetime import datetime, timezone

    from .. import applog, runtime_state

    logger = applog.get_logger("mcp")

    existing = runtime_state.read_runtime_file("mcp")
    if existing is not None and existing.get("root") == root:
        logger.info(f"already running for {root} at {existing.get('url')}; "
                    "not starting a second instance")
        return 0

    port = _pick_loopback_port(preferred_port)
    url = f"http://127.0.0.1:{port}"
    logger.info(f"citevahti-mcp (streamable-http): root={root} url={url}")
    runtime_state.write_runtime_file(
        "mcp", url=url, pid=os.getpid(), root=root,
        started_at=datetime.now(timezone.utc).isoformat())

    def _handler(signum, frame):
        runtime_state.clear_runtime_file("mcp")
        os._exit(0)

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
    if parent_pid:
        # After the SIGTERM handler exists, so an orphaning clears the handshake file —
        # an agent server must never outlive the shell the user thinks controls it.
        from ..parentwatch import watch_parent

        watch_parent(parent_pid)
    try:
        build_server(root=root, host="127.0.0.1", port=port).run(transport="streamable-http")
    finally:
        runtime_state.clear_runtime_file("mcp")
    return 0


def main(argv=None) -> int:
    import argparse
    import sys
    from pathlib import Path

    from ..rootcfg import default_root

    parser = argparse.ArgumentParser(prog="citevahti-mcp",
                                     description="Serve the constrained CiteVahti agent tools over MCP.")
    # STABLE root — explicit --root, else $CITEVAHTI_ROOT, else the home dir. NEVER cwd:
    # the desktop app launches this server with an arbitrary cwd (often /), so a
    # cwd-relative default would never find the ledger `citevahti init` created.
    parser.add_argument("--root", default=default_root(),
                        help="project root holding .citevahti/ (default: $CITEVAHTI_ROOT or your home folder)")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio",
                        help="'stdio' (default — the Claude Desktop .mcpb path) or "
                             "'streamable-http' (loopback only; the desktop app's supervised "
                             "agent-server sidecar path)")
    parser.add_argument("--port", type=int, default=8766,
                        help="preferred loopback port for --transport streamable-http (falls "
                             "back to an available port if taken); ignored for stdio")
    parser.add_argument("--parent-pid", type=int, default=None,
                        help="exit when this supervising process dies (passed by the "
                             "CiteVahti.app shell; standalone and stdio runs leave it unset)")
    args = parser.parse_args(argv)
    root = str(Path(args.root).expanduser().resolve())

    if args.transport == "streamable-http":
        return _serve_streamable_http(root, args.port, parent_pid=args.parent_pid)

    from .. import __version__
    # stdout is the MCP protocol channel — startup diagnostics go to stderr. The version
    # lets you confirm a re-uploaded .mcpb is the latest build (Claude Desktop caches it).
    print(f"citevahti-mcp v{__version__}: ledger root = {root} "
          f"({root}/.citevahti/config.json) — run the 'init' tool first if it doesn't exist yet.",
          file=sys.stderr)
    build_server(root=root).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
