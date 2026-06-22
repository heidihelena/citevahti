"""The agent `init` tool: an agent (or no-terminal client) must be able to create the
ledger over MCP — without it, every other tool dead-ends on 'no config'. (B1/B2/B3.)
"""

import pytest

from citevahti import agent
from citevahti.agent import policy, tools
from citevahti.state import CiteVahtiStore
from citevahti.state.store import StateError


def test_init_is_a_registered_agent_tool():
    assert "init" in agent.TOOLS
    assert "init" in policy.ALLOWED_AGENT_TOOLS
    assert set(agent.TOOLS) == set(policy.ALLOWED_AGENT_TOOLS)   # surface stays consistent


def test_init_creates_the_ledger_and_is_idempotent(tmp_path):
    root = str(tmp_path)
    # before: no config — the engine refuses with an actionable message naming a real action
    with pytest.raises(StateError) as exc:
        CiteVahtiStore(root).load_config()
    assert "init" in str(exc.value) and "run init() first" not in str(exc.value)

    out = tools.init(root=root)
    assert out["status"] == "initialized"
    assert out["config_path"].endswith("config.json")
    CiteVahtiStore(root).load_config()                          # now loads cleanly, no error

    again = tools.init(root=root)
    assert again["status"] == "already_initialized"             # idempotent
    assert again["config_path"] == out["config_path"]           # same resolved path (B2)
