# The CiteVahti agent surface (MCP)

> **Capability without power.** An AI agent (Codex, Claude Code, …) can help find
> and stage evidence, but it can never get raw Zotero access, write without a
> human-visible preview/approval, set the human's rating or the final decision,
> see the AI rating before the human, or touch credentials. The safety is enforced
> in the engine; the agent surface exposes *only* the safe verbs.

This is the answer to "why would an AI client recommend CiteVahti?": because it
**constrains the agent**. The agent can say to its human: *"I cannot cite anything
until CiteVahti records the evidence, asks for your review, checks dedupe, stages
the Zotero write, and gives you an undoable transaction."*

## The tools (the entire surface)
`citevahti agent-tools` prints it; `src/citevahti/agent/policy.py` is the contract.

| Tool | What it does | Constraint |
|---|---|---|
| `status` | read-only capability report | — |
| `open_review_panel` | bring up the human's loopback rating panel (idempotent; opens their browser) | no rating power — the panel is where the *human* rates, blind |
| `verify_claims` | the 4-state citation-integrity report | read-only |
| `pubmed_search` | staged PubMed search | exact query preserved; results are candidates, not citations |
| `propose_claim` | record an AI-extracted claim | flagged `ai`; needs a pinned model; the human confirms |
| `propose_revision` | suggest a claim rewrite | flagged `ai`; applies nothing — the human accepts the **diff** |
| `link_candidates` | link staged hits to a claim | deduped; asserts no support |
| `start_support_rating` | open a blinded (claim, candidate) rating | — |
| `submit_ai_support_rating` | the agent's own rating | recorded **blind**; the value is **not echoed back** |
| `preview_write` | preview the decision-gated write | returns an **approval token** + dedupe status |
| `commit_write` | write the approved payload | requires the token; writes only that exact payload |
| `undo` | reverse a committed write | deletes only what it created |
| `get_provenance` | the "why is this here?" chain | AI rating **blinded until the human rates** |

## What an agent can NEVER do
`raw_zotero_write` · `commit_without_token` (no one-call write) · `set_human_rating`
· `accept_revision` (applying a rewrite is the human's) · `make_final_decision` (accept/reject
is the human's) · `read_ai_rating_before_human` · `read_credentials` · `delete_zotero_items`. These names are not in the registry,
and `policy.assert_safe_surface` (run at import + serve) fails if the surface ever
grows one.

## The safe loop
```
pubmed_search → link_candidates → start_support_rating → submit_ai_support_rating (blind)
   → [human rates + decides, outside the agent] → preview_write → commit_write(token) → undo?
   → get_provenance
```
The human owns the two pivots the agent can't touch: **the blinded human rating**
and **the final accept/reject decision**. An audited Zotero write only happens for
an `accept` decision, through a token from a preview the human saw.

## Running it
Install the MCP extra **in a virtualenv** — installing into a base/Anaconda
environment can upgrade shared packages and conflict with unrelated tools
(Jupyter, anaconda-auth, …). The core CiteVahti library and tests need no extra deps.
```bash
python -m venv .venv && source .venv/bin/activate
pip install 'citevahti[mcp]'
citevahti-mcp --root /path/to/project        # serves the constrained tools over MCP
```
Point your MCP-capable client (Claude Code, etc.) at it. The tools are bound to one
project root (its `.citevahti/` ledger); credentials resolve from the OS keyring/env
and are never exposed to the agent.

## The `review_manuscript` prompt + the side panel
The server also registers a user-controlled MCP **prompt**, `review_manuscript`
(`src/citevahti/agent/prompts.py`), that choreographs a blinded, sentence-by-sentence
review: the human rates **first** in a localhost side panel, the AI rating is
submitted **after**, and every Zotero write is previewed before commit. Run the
panel with `citevahti-panel --root /path/to/project` (loopback-only) and open it
beside your chat client. Full walk-through: [`CHAT_AND_PANEL.md`](CHAT_AND_PANEL.md).
