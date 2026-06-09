# Run unit tests on a manuscript

The frame: **the manuscript is the code, each claim is a test, CiteVahti runs the
evidence tests before you cite.** You drive it from a chat client (Codex, Claude
Code, Claude Desktop, ChatGPT) connected to the CiteVahti MCP server, and you record
your blind ratings in a localhost side panel.

> The human rates first. The AI second opinion stays hidden until then. Zotero
> writes are previewed, confirmed, and undoable.

## 1. Start the CiteVahti MCP server

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[mcp]'
citevahti init                       # creates the .citevahti/ ledger here
citevahti-mcp --root /path/to/project
```

## 2. Connect Codex or Claude Code

Stdio MCP server config (same block works for Claude Desktop / ChatGPT desktop):

```json
{
  "mcpServers": {
    "citevahti": { "command": "citevahti-mcp", "args": ["--root", "/path/to/project"] }
  }
}
```

- **Claude Code:** `claude mcp add citevahti -- citevahti-mcp --root /path/to/project`
- **Codex:** add the equivalent stdio entry in `config.toml`.

## 3. Open the side panel beside the chat

```bash
citevahti-panel --root /path/to/project        # http://127.0.0.1:8765, loopback only
```

## 4. Run the claim-tests

1. Paste or attach the manuscript text in the chat, and invoke the
   **`run_claim_tests`** prompt (the deprecated `review_manuscript` alias also works).
2. The agent walks it **paragraph by paragraph**, picks one claim at a time, and
   treats each as a **test case**. It resolves the current citation (flagging a
   `reference_broken` or `reference_hallucinated` reference), searches PubMed for
   candidates, checks the Zotero dedupe status, and weighs **meaning, not topic**
   (PICO fit — a paper existing is not the same as it supporting the claim).
3. **You rate first, in the panel.** The agent will not state its rating yet.
4. After your rating is recorded, the agent submits its **AI second rating** and
   reveals agreement or disagreement (the engine unblinds it only once you've rated).
5. Adjudicate any disagreement; **you** own the final decision.
6. Each claim lands in a state: **`[oo]` verified · `[o]` needs support · `[r]`
   review needed · `[d]` decided.**
7. To cite: **preview** the Zotero write, **confirm** it, and **undo** if needed —
   nothing is written silently.

## 5. Export the claim-test report

```bash
citevahti report                      # the Claim Test Report (text-framed)
citevahti report --format md          # Markdown, e.g. for a supervisor or editor
citevahti report --format json        # structured, e.g. for the VS Code extension
```

The report is a **test summary** plus per-claim detail:

```
## Summary
- [oo] verified: 8
- [o] needs support: 3
- [r] review needed: 2
- [d] decided: 6
```

Per claim it shows the claim id and text, the current citation, the evidence
candidate, a **finding label** (e.g. `support_direct`, `related_but_insufficient`,
`reference_real_but_wrong`, `overclaim`), your rating, the AI rating **only if you
have rated**, the final decision, the Zotero action, and provenance. The finding
vocabulary is stable — see `src/citevahti/findings.py`.

## What stays true

- You rate **before** the AI rating is visible **in the panel** — the panel/report read
  paths withhold it until your rating exists (not the LLM's good behaviour). It's a
  panel-enforced workflow, not a hard engine lock (the CLI/raw ledger can surface it
  earlier); the ledger records the rating order/mode so blind-first is auditable.
- No Zotero write happens without a preview and your explicit confirmation; every
  write is undoable; raw Zotero writes are never exposed.
- MCP is the **spine**, not the product: it lets agents run the workflow. VS Code is
  one adapter; the full web editor and remote (Streamable-HTTP) transport are the
  paid hosted tier (ADR-0003), not this local tool.

See [`../adr/0007-local-web-app-and-http-surface.md`](../adr/0007-local-web-app-and-http-surface.md)
and [`../CHAT_AND_PANEL.md`](../CHAT_AND_PANEL.md).
