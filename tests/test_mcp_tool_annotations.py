"""Every MCP tool must carry a title + safety hints (Anthropic directory hard gate),
and the read-only classification must be *honest* — cross-checked against the tools
proven side-effect-free in test_readonly_tools_dont_mutate.py.

Offline: builds the stdio server and reads back what the protocol would advertise.
"""

from __future__ import annotations

import pytest

from citevahti import agent
from citevahti.agent.annotations import TOOL_META, assert_annotations_complete

# The tools test_readonly_tools_dont_mutate.py drives and asserts leave the ledger
# byte-identical. Anything marked readOnlyHint=True must be in this proven-safe set;
# a mutating tool mislabeled read-only would tell a client (and a user) it's safe to
# run without confirmation when it isn't.
_PROVEN_READONLY = {
    "status", "verify_claims", "triage", "methods", "model_advisor", "claim_bond_status",
    # read-only by construction (search/fetch/preview; no ledger write)
    "check_update", "check_paragraph", "pubmed_search", "get_provenance", "preview_write",
}


def test_every_tool_has_metadata_and_titles_fit():
    assert_annotations_complete(agent.TOOLS.keys())   # raises on drift / >64-char title


def test_readonly_hints_are_a_subset_of_the_proven_non_mutating_tools():
    claimed = {n for n, m in TOOL_META.items() if m.read_only}
    liar = claimed - _PROVEN_READONLY
    assert not liar, f"tools claim readOnlyHint but aren't proven side-effect-free: {sorted(liar)}"


def test_the_zotero_write_is_the_destructive_open_world_tool():
    cw = TOOL_META["commit_write"]
    assert cw.read_only is False and cw.destructive is True and cw.open_world is True
    # the pre-write preview must NOT be destructive — it computes, it doesn't write
    assert TOOL_META["preview_write"].read_only is True


def test_external_calls_are_marked_open_world():
    for name in ("pubmed_search", "check_update", "commit_write"):
        assert TOOL_META[name].open_world is True, f"{name} touches an external system"


def test_annotations_surface_over_the_protocol():
    """What a Claude Desktop client actually receives: title + hints on every tool."""
    pytest.importorskip("mcp")
    import citevahti.agent.mcp_server as mcp_server

    server = mcp_server.build_server(root=".")
    by_name = {t.name: t for t in server._tool_manager.list_tools()}
    assert set(by_name) == set(agent.TOOLS)
    for name, t in by_name.items():
        ann = t.annotations
        assert ann is not None and ann.title, f"{name} has no title/annotations"
        assert ann.readOnlyHint is TOOL_META[name].read_only
    # the one external write is advertised destructive; a read tool is advertised read-only
    assert by_name["commit_write"].annotations.destructiveHint is True
    assert by_name["status"].annotations.readOnlyHint is True
