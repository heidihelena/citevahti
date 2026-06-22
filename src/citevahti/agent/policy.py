"""Agent tool policy — the constrained surface an AI agent may call.

The product promise to an AI client is *capability without power*: an agent can
help find and stage evidence, but it can never get raw Zotero access, write
without a human-visible preview/approval, set the human's rating or the final
decision, see the AI rating before the human rates, or touch credentials. Those
guarantees are enforced in the engine; this module states them explicitly and is
asserted by tests so the surface can never silently grow a dangerous verb.
"""

from __future__ import annotations

# The ONLY tools exposed to an agent (MCP / function-calling). Anything not here
# is unreachable by an agent.
ALLOWED_AGENT_TOOLS = (
    "init",                      # create the project ledger (idempotent); every tool needs it
    "status",                    # read-only capability report
    "triage",                    # read-only risk-first "what needs your attention" list
    "check_paragraph",           # read-only: match a pasted snippet's sentences to vetted claims
    "open_review_panel",         # bring up the human's loopback rating surface (no rating power)
    "verify_claims",             # read-only 4-state citation-integrity report
    "pubmed_search",             # staged, exact-query-preserving PubMed search
    "propose_claim",             # AI-extracted claim (flagged; human confirms)
    "propose_revision",          # AI-suggested rewrite (flagged; human accepts the diff)
    "link_candidates",           # link staged hits to a claim
    "start_support_rating",      # open a blinded (claim, candidate) rating
    "submit_ai_support_rating",  # the agent's own rating, recorded BLIND (no echo)
    "preview_write",             # returns an approval token + dedupe status
    "commit_write",              # writes ONLY the approved payload (token-bound)
    "undo",                      # reverse a committed write
    "get_provenance",            # read the "why is this here?" chain
    "claim_bond_status",         # read-only: flag evidence assessments stale after a claim revision
)

# Capabilities an agent must NEVER have. Asserted against the surface in tests.
FORBIDDEN_AGENT_CAPABILITIES = (
    "raw_zotero_write",          # only constrained, decision-gated writes
    "commit_without_token",      # no one-call write; a preview/approval is required
    "set_human_rating",          # the human's blinded rating is human-only
    "accept_revision",           # applying a rewrite to the claim is human-only (never silent)
    "make_final_decision",       # accept/reject is the human's call
    "read_ai_rating_before_human",  # blinding: AI hidden until the human rates
    "read_credentials",          # keys never reachable
    "delete_zotero_items",       # destructive ops disabled (undo deletes only our own creates)
)


def assert_safe_surface(tool_names) -> None:
    """Fail loudly if the exposed surface includes anything not on the allow-list."""
    extra = sorted(set(tool_names) - set(ALLOWED_AGENT_TOOLS))
    if extra:
        raise AssertionError(f"agent surface exposes non-allowed tools: {extra}")
