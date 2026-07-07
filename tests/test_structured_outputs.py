"""Every agent tool returns a structured (JSON dict) output — never free text.

Roadmap item #6. MCP clients consume tool results as machine-readable data; a tool that
returned a bare string (or a non-serializable object) would break that contract and could
smuggle unstructured content past the schema. Every tool in the surface already returns a
dict — this locks it so a future tool can't quietly regress.
"""

from __future__ import annotations

import json
import typing

from citevahti import agent


def test_every_agent_tool_declares_a_dict_return():
    """Static contract: every tool in the surface annotates `-> dict`."""
    bad = {name: typing.get_type_hints(fn).get("return")
           for name, fn in agent.TOOLS.items()
           if typing.get_type_hints(fn).get("return") is not dict}
    assert not bad, f"agent tools must return dict (structured output); offenders: {bad}"


def test_tool_outputs_are_json_serializable_dicts(tmp_path):
    """Runtime contract: the tools callable on a fresh ledger return JSON-serializable dicts
    (no exotic objects). The state-dependent tools — preview/commit/undo/provenance — are
    covered by the static annotation check above and their own behavioural tests."""
    root = str(tmp_path)
    agent.tools.init(root=root)
    calls = {
        "init": lambda: agent.tools.init(root=root),
        "status": lambda: agent.tools.status(root=root),
        "triage": lambda: agent.tools.triage(root=root),
        "verify_claims": lambda: agent.tools.verify_claims(root=root),
        "methods": lambda: agent.tools.methods(root=root),
        "model_advisor": lambda: agent.tools.model_advisor(root=root),
        "check_paragraph": lambda: agent.tools.check_paragraph("A sentence to check.", root=root),
    }
    for name, call in calls.items():
        out = call()
        assert isinstance(out, dict), f"{name} returned {type(out).__name__}, not a dict"
        json.dumps(out)   # raises if the dict carries anything non-JSON — must not
