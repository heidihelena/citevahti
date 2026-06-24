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


def build_server(name: str = "citevahti", *, root: str = "."):
    """Build a FastMCP server with the constrained tools bound to ``root``.

    Raises a clear error if the ``mcp`` package isn't installed.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "the 'mcp' package is required to serve (pip install 'citevahti[mcp]')") from exc

    assert_safe_surface(TOOLS.keys())          # defense in depth at serve time
    server = FastMCP(name)

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
    args = parser.parse_args(argv)
    root = str(Path(args.root).expanduser().resolve())
    # stdout is the MCP protocol channel — startup diagnostics go to stderr.
    print(f"citevahti-mcp: ledger root = {root} ({root}/.citevahti/config.json) — "
          "run the 'init' tool first if it doesn't exist yet.", file=sys.stderr)
    build_server(root=root).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
