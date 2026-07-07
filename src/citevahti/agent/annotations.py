"""Per-tool presentation + safety metadata for the MCP surface.

Every tool the agent can call carries a human-readable ``title`` and MCP safety
*hints* (``readOnlyHint`` / ``destructiveHint`` / ``idempotentHint`` /
``openWorldHint``). These drive the client's own guardrails — a host may show a
confirmation before a non-read-only call — and they are a hard gate for Anthropic's
software directory. They are *hints*, advisory to clients; CiteVahti's real
enforcement is the constrained surface (``policy.py``) and the decision-gated,
token-confirmed Zotero write path — never a client honouring a flag.

The read-only classification here is safety-relevant, so it is cross-checked in
``tests/test_mcp_tool_annotations.py`` against the tools proven side-effect-free by
``tests/test_readonly_tools_dont_mutate.py`` — a tool cannot claim ``readOnlyHint``
here while mutating the ledger there.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolMeta:
    title: str                       # human-readable, <= 64 chars (directory rule)
    read_only: bool
    destructive: bool = False        # only meaningful when read_only is False
    idempotent: bool = False         # only meaningful when read_only is False
    open_world: bool = False         # touches an external system (PyPI, PubMed, Zotero)


# Keyed by the exact tool name in ``agent.TOOLS``. Parity with that registry is
# asserted at import (below) and in the test — a new tool without an entry fails fast.
TOOL_META: dict[str, ToolMeta] = {
    # ---- read-only: search / fetch / report; never modify the ledger ----------
    "status": ToolMeta("Show CiteVahti status and connections", read_only=True),
    "getting_started": ToolMeta("Show where to start and your single next step",
                                read_only=True, open_world=True),
    "check_update": ToolMeta("Check PyPI for a newer CiteVahti release",
                             read_only=True, open_world=True),
    "triage": ToolMeta("List the claims that need your attention, worst first", read_only=True),
    "check_paragraph": ToolMeta("Check a drafted paragraph against your reviewed claims",
                                read_only=True),
    "methods": ToolMeta("Draft the methods statement and PRISMA disclosure", read_only=True),
    "model_advisor": ToolMeta("Advise which AI model to trust as a second opinion",
                              read_only=True),
    "verify_claims": ToolMeta("Re-check the ledger's integrity", read_only=True),
    "pubmed_search": ToolMeta("Search PubMed for candidate papers",
                              read_only=True, open_world=True),
    "get_provenance": ToolMeta("Show a claim's evidence and decision provenance", read_only=True),
    "claim_bond_status": ToolMeta("Show whether a claim's assessment is still current",
                                  read_only=True),
    "preview_write": ToolMeta("Preview a Zotero write without performing it", read_only=True),

    # ---- write, non-destructive: additive/corrective ledger changes -----------
    "init": ToolMeta("Create the CiteVahti ledger for this project",
                     read_only=False, idempotent=True),
    "propose_claim": ToolMeta("Add a claim to the ledger", read_only=False),
    "propose_revision": ToolMeta("Propose a revision to a claim", read_only=False),
    "link_candidates": ToolMeta("Attach candidate papers to a claim as evidence", read_only=False),
    "start_support_rating": ToolMeta("Open a claim-support rating", read_only=False),
    "submit_ai_support_rating": ToolMeta("Record the AI's blinded second rating",
                                         read_only=False),
    "undo": ToolMeta("Undo the last write or edit", read_only=False),
    "open_review_panel": ToolMeta("Open the human review panel", read_only=False),

    # ---- destructive / external: the one write that leaves the machine --------
    "commit_write": ToolMeta("Write the decided citation to your Zotero library",
                             read_only=False, destructive=True, open_world=True),
}


def annotations_kwargs(name: str) -> dict:
    """The ``title=`` and ``annotations=ToolAnnotations(...)`` kwargs for ``FastMCP.tool``.

    Imports ``mcp`` lazily so importing this module never requires the optional
    ``[mcp]`` extra (the classification itself is pure data, used by tests too).
    """
    from mcp.types import ToolAnnotations

    m = TOOL_META[name]
    ann = ToolAnnotations(
        title=m.title,
        readOnlyHint=m.read_only,
        destructiveHint=(m.destructive if not m.read_only else None),
        idempotentHint=(m.idempotent if not m.read_only else None),
        openWorldHint=(m.open_world or None),
    )
    return {"title": m.title, "annotations": ann}


def assert_annotations_complete(tool_names) -> None:
    """Every registered tool must have metadata, and every title must fit the 64-char
    directory limit. Called at import so the surface and its metadata can't drift apart."""
    names = set(tool_names)
    missing = names - set(TOOL_META)
    if missing:
        raise AssertionError(f"tools without annotation metadata: {sorted(missing)}")
    extra = set(TOOL_META) - names
    if extra:
        raise AssertionError(f"annotation metadata for unknown tools: {sorted(extra)}")
    too_long = [n for n, m in TOOL_META.items() if len(m.title) > 64]
    if too_long:
        raise AssertionError(f"tool titles exceed 64 chars: {too_long}")
