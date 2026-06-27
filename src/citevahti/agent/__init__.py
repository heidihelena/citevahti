"""CiteVahti agent surface: the constrained tools an AI agent may call.

Capability without power — find/stage/preview/commit-with-token/undo, but no raw
Zotero access, no one-call write, no human-rating or final-decision authority, no
peeking at the AI rating before the human. The registry below is the *entire*
surface; `policy.assert_safe_surface` guarantees it never grows a dangerous verb.
"""

from __future__ import annotations

from . import tools
from .policy import ALLOWED_AGENT_TOOLS, FORBIDDEN_AGENT_CAPABILITIES, assert_safe_surface

# The complete agent tool registry (name -> callable). MCP/function-calling
# servers build directly from this; nothing outside it is reachable by an agent.
# Output contract: every tool returns a structured JSON `dict` — never free text —
# so clients can parse results reliably (locked by tests/test_structured_outputs.py).
TOOLS = {
    "init": tools.init,                  # create the ledger — every other tool needs it first
    "status": tools.status,
    "check_update": tools.check_update,  # read-only, user-initiated: is a newer release on PyPI?
    "triage": tools.triage,              # risk-first "what needs you" — review the few, not all
    "check_paragraph": tools.check_paragraph,  # everyday in-writing loop: vetted / needs-attention / new
    "methods": tools.methods,            # submission methods paragraph + PRISMA LLM-discovery disclosure

    "open_review_panel": tools.open_review_panel,
    "verify_claims": tools.verify_claims,
    "pubmed_search": tools.pubmed_search,
    "propose_claim": tools.propose_claim,
    "propose_revision": tools.propose_revision,
    "link_candidates": tools.link_candidates,
    "start_support_rating": tools.start_support_rating,
    "submit_ai_support_rating": tools.submit_ai_support_rating,
    "preview_write": tools.preview_write,
    "commit_write": tools.commit_write,
    "undo": tools.undo,
    "get_provenance": tools.get_provenance,
    "claim_bond_status": tools.claim_bond_status,
}

# fail fast at import if the surface ever drifts from the allow-list
assert_safe_surface(TOOLS.keys())

__all__ = [
    "TOOLS",
    "tools",
    "ALLOWED_AGENT_TOOLS",
    "FORBIDDEN_AGENT_CAPABILITIES",
    "assert_safe_surface",
]
