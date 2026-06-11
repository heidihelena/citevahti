# ADR-0007 — Two co-primary surfaces: a conversation (MCP prompt) for orchestration + a localhost side panel for the blind human rating; VS Code is one adapter

- **Status:** Accepted (2026-06-06)
- **Relates to:** ADR-0001 (the ledger + the blinded method), ADR-0002 (the inline
  review layer), ADR-0003 (open core / hosted boundary), ADR-0005 (Zotero auth &
  write-back). **Refines ADR-0002** — keeps its `[oo/o/r/d]` semantics and inline
  interaction model as the reference design, and **supersedes ADR-0002 §6's build
  order in part** (§6 below).
- **Customer steer (decisive for the local/free tier):** the customer dislikes
  IDEs and wants to *talk to an LLM* (Claude Desktop / ChatGPT / Claude Code /
  Codex), attach the manuscript, and walk it sentence by sentence — **and** to keep
  the inline review card for their *own* decisions. So the surface is split in two.

## 1. Context

ADR-0002 chose a VS Code extension as the first inline surface; it ships (v0.8.0)
and proves the interaction model. But VS Code is a builder's host, hostile to a
researcher whose only question is "does this paper support this sentence?" Two
things became clear from the customer:

1. The natural orchestration surface is a **conversation** — attach/paste the
   manuscript and walk it claim by claim with an LLM that already has the CiteVahti
   MCP tools.
2. The customer still wants the **inline card** to make their *own* call — but the
   moment an LLM in chat answers "does this support it?", the human has seen the AI
   opinion before forming their own. A free-form chat silently breaks ADR-0001's
   blinded method.

The resolution: **two co-primary surfaces.** Chat handles triage, manuscript
walking, candidate discovery, and the AI-side reasoning. A separate **localhost
side panel** is the *blind human decision surface* — physically separate from the
chat, so the human rates before any AI opinion is visible. Blinding becomes a
property of the architecture, not of the LLM's good behaviour.

**What already exists (do not rebuild).** The MCP spine is the most-tested part of
the system and is exactly what the conversation needs:

- MCP server over **stdio** — [`src/citevahti/agent/mcp_server.py`](../../src/citevahti/agent/mcp_server.py).
- A constrained tool surface over the engine —
  [`src/citevahti/agent/tools.py`](../../src/citevahti/agent/tools.py).
- "Reads agentic, writes gated", enforced + test-asserted —
  [`src/citevahti/agent/policy.py`](../../src/citevahti/agent/policy.py).
- Blinding enforced **in the engine**: the AI value is never echoed and is hidden
  until a human rating exists.

**What is missing (this ADR's v1 scope).** (a) An MCP **prompt** to choreograph the
chat loop (the server registers tools only). (b) A **thin localhost HTTP API** for
the side panel — *only* the decision surface, not a manuscript editor. (c) Wiring
the existing static inline mockup ([`mockups/citevahti-inline/`](../../mockups/citevahti-inline/index.html))
to that API.

## 2. Decision

1. **Two co-primary researcher surfaces.**
   - **Conversation (orchestration):** an LLM client connected to the existing MCP
     server, driven by a CiteVahti **MCP prompt** (§3). It does triage, walks the
     manuscript, proposes/verifies claims, searches/links PubMed candidates, and
     produces the AI-side rating — *through the existing constrained tools.*
   - **Localhost side panel (blind human decision):** a narrow browser panel served
     from `127.0.0.1`, reusing the ADR-0002 inline card, where the human records
     their **blind support rating** before any AI opinion is shown.

2. **The panel preserves the blind by construction.** It is a separate window from
   the chat and its read endpoints obey the engine's blinding: the AI rating is
   never returned until a human rating exists for that (claim, candidate). The human
   rates first *in the panel*; the chat reveals the AI rating *after*.

3. **A thin localhost HTTP API returns to v1 — scoped to the decision panel only.**
   It maps onto existing engine/agent functions (no new evidence/safety logic),
   binds to **loopback only** by default, and is the minimum needed to wire the
   panel: health, list claims, one claim's evidence card, start/submit *human*
   rating, blinded rating/provenance status, and the guarded write preview → commit
   → undo (reusing the token-gated agent wrappers). **No** raw Zotero write, **no**
   agent-made final decision, **no** credential endpoint, **no** AI-before-human.

4. **`LLMProvider` stays deferred.** In the conversational topology the chat LLM
   *is* the AI rater (topology (a)); no app-internal provider is needed for v1.

5. **The full web app / manuscript editor + Streamable-HTTP belong to the paid
   hosted tier, not this product.** The free local-first tool ships the chat + the
   loopback panel only. A full web editor and Streamable-HTTP / remote transport are
   **hosted-tier infrastructure (ADR-0003)** — Vahtian's paid layer for
   organizations — not a "later free" feature. The panel is a decision surface, not
   an editor.

6. **VS Code is demoted to one adapter — not deleted.** Its inline interaction model
   (claim spans, the evidence card, `[oo/o/r/d]`) is the **reference design** the
   panel reuses. Other adapters (Word, Docs/Overleaf, Zotero pane) remain later,
   optional, each a thin client over the same engine.

## 3. The blinded loop the MCP prompt choreographs

The prompt drives the *conversation*; the panel records the *human* decision; the
engine enforces the invariants. The LLM is instructed to:

1. Accept a manuscript paragraph / section / attached text.
2. Identify **one** candidate claim at a time.
3. Propose or verify that claim via the existing tools (`propose_claim` /
   `verify_claims`).
4. Search / link candidate PubMed evidence via the existing tools
   (`pubmed_search` / `link_candidates`).
5. **Direct the human to rate in the localhost side panel before revealing any AI
   judgment**, and **not** state the AI support rating until the human's is recorded.
6. After the human rating is recorded, submit the AI rating via
   `submit_ai_support_rating`.
7. Reveal agreement/disagreement only after the engine permits provenance access
   (`get_provenance` — blinded until the human has rated).
8. Ask for adjudication only once **both** ratings exist.
9. Preview the Zotero write (`preview_write`) before any commit.
10. Never commit (`commit_write`) without explicit user confirmation; mention
    **undo** availability after commit.

If asked for its opinion before step 5, the prompt instructs the LLM to withhold it
and point the user to the panel — protecting the blind is part of the contract.

## 4. Claim extraction in v1

`extract/` is field extraction, not claim segmentation, and there is no batch
`claim.extract` tool. The chat LLM segments the manuscript into candidate claim
sentences and calls `propose_claim` per sentence (flagged ai-extracted, awaiting
human confirmation). No new extraction engine is built in this ADR.

## 5. Safety posture (carried forward, unchanged)

- Every surface renders engine state and **re-implements no integrity logic**; the
  panel's write path **reuses the token-gated agent wrappers** (`preview_write` →
  `commit_write` → `undo`).
- Writes stay decision-gated; a confirmed write requires a prior preview's token.
- The AI rating is **blinded in the engine and in every panel read endpoint** until
  the human has rated.
- The HTTP API **binds to loopback (`127.0.0.1`) only**; it is never exposed
  externally and adds no telemetry.
- The `policy.ALLOWED_AGENT_TOOLS` allow-list remains authoritative; the panel
  introduces **no new agent capability** and does not grow `agent.TOOLS`.
- Zotero local API stays read-only; deleting/overwriting Zotero data is never in
  scope; the audit log stays hash-chained; secrets stay in the OS keychain
  (ADR-0005).

## 6. Supersedes — ADR-0002 §6 build order (in part)

ADR-0002 §6 read "1. VS Code extension … 2. Then a web editor." VS Code is built;
this ADR makes the **conversation + localhost side panel** the primary front door,
reclassifies VS Code as one adapter, and keeps the full web editor deferred.
ADR-0002's design is unchanged and is the panel's reference.

## 7. Consequences

- **Positive:** the customer works where they already are (chat) and keeps the
  inline card for their own calls; blinding is enforced by *physical separation*,
  not LLM discipline; v1 is small (one MCP prompt + a thin loopback API + wiring an
  existing mockup) with no new engine, provider, or safety logic; agents become
  interchangeable assistants around CiteVahti.
- **The risk this ADR neutralizes:** a conversational surface silently destroying
  the blinded method. The panel + the prompt's withhold-until-rated contract remove
  that risk.
- **Cost / scope:** the MCP prompt (text + ordering assertions); a stdlib loopback
  HTTP server mapping to existing functions; adapting the static mockup to fetch
  from it. Two new thin layers; no new dependency.
- **Deferred for the free tier:** `LLMProvider` (incl. `none`) — its own ADR if
  pursued. **Paid hosted tier (ADR-0003), not this product:** the full web
  app/editor and Streamable-HTTP / remote transport.
- **Carried forward:** read-only Zotero local API; decision-gated, undoable writes;
  no silent edits; workflow-enforced, audit-verified blinding (the AI seam is
  structurally blind to the human value; the human-first order is enforced by the
  panel workflow and logged); keychain secrets (ADR-0005); the
  open-core boundary (ADR-0003) — MCP server, prompt, HTTP API, and panel are all
  Apache-2.0 core.

## 8. Build target order (this PR)

1. **MCP prompt** choreographing the blinded review loop (§3), bound on the existing
   FastMCP server next to the tools; ordering asserted in tests.
2. **Thin loopback HTTP API** over existing functions (health, claims, evidence
   card, start/submit human rating, blinded status/provenance, preview/commit/undo).
3. **Wire the inline mockup** as the panel: evidence card, claim navigation, human
   rating controls, status, provenance-only-after-allowed, write controls.
4. **Setup doc** for the v1 workflow (connect MCP client + open the panel beside it).
5. *(Free tier, deferred — own ADR)* `LLMProvider`. *(Paid hosted tier, ADR-0003)*
   the full web editor + Streamable-HTTP transport — not this product.
