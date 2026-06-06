# Chat + side panel — the v1 workflow (ADR-0007)

Two surfaces, side by side:

- **A chat client** (Claude Desktop, ChatGPT desktop, Claude Code, Codex) connected
  to the CiteVahti **MCP server**. It walks the manuscript, finds candidates, and
  records the AI second rating — through the constrained tools (see
  [`AGENT.md`](AGENT.md)).
- **A localhost side panel** where *you* record your blind support rating before the
  chat reveals the AI's. The AI rating stays hidden until your rating exists.

You keep both open. You rate in the panel; the chat reveals the AI rating after.

## 1. Install (in a virtualenv)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[mcp]'        # MCP server needs the extra; the panel needs no extra deps
citevahti init                 # creates the .citevahti/ ledger in this folder
```

## 2. The one-command path: `citevahti start`

One command brings up the whole workspace — and it doubles as the single line you
put in your chat client's MCP config. When the client launches it, `start`
side-launches the loopback panel + browser in the background, prints plain
next-step prompts (to stderr), then serves the MCP tools over stdio:

```json
{
  "mcpServers": {
    "citevahti": {
      "command": "citevahti",
      "args": ["start", "--root", "/path/to/project"]
    }
  }
}
```

You can also run it yourself in a terminal — but note it then **takes over that
terminal**: it serves the MCP protocol on stdin (so no shell prompt comes back)
with the panel running in the background, and the panel stays empty until a claim
exists. To just bring the panel up for hands-on/CLI work, prefer `citevahti-panel`
(§3) and use a second terminal for commands; `start` is primarily the line your
chat client spawns. (`--port` changes the port, `--no-browser` skips opening a
window. If the `mcp` extra isn't installed, `start` still leaves the panel
running.)

The manual, three-step path below is equivalent if you'd rather wire each surface
yourself.

## 2b. Start the MCP server and connect a chat client (manual)

```bash
citevahti-mcp --root /path/to/project
```

Point an MCP-capable client at it (stdio). Example client config:

```json
{
  "mcpServers": {
    "citevahti": {
      "command": "citevahti-mcp",
      "args": ["--root", "/path/to/project"]
    }
  }
}
```

- **Claude Desktop / ChatGPT desktop:** add the block above to the app's MCP config.
- **Claude Code:** `claude mcp add citevahti -- citevahti-mcp --root /path/to/project`.
- **Codex:** add the equivalent stdio server entry in `config.toml`.

The server exposes the constrained tools **and** a user-invokable prompt,
`run_claim_tests`, which choreographs the blinded loop (it tells the LLM to make
you rate first and to gate every write). (`review_manuscript` is kept as a
deprecated alias for clients that connected via 0.9.0.)

## 3. Start the side panel

```bash
citevahti-panel --root /path/to/project        # http://127.0.0.1:8765, loopback only
```

Open `http://127.0.0.1:8765` in a browser window next to your chat. (Use `--port`
to change the port. It binds to `127.0.0.1`; do not expose it externally.)

## 4. Walk the manuscript

1. In the chat, run the **`run_claim_tests`** prompt (or just paste/attach a
   paragraph and ask CiteVahti to review it claim by claim).
2. The chat proposes one claim, searches PubMed, and links a candidate — then tells
   you to rate in the panel. **It will not state its own rating yet.**
3. In the **panel**, pick the claim, read the candidate, and press your support
   rating. That is your blind rating.
4. Back in the chat, it submits the AI second rating and reveals agreement or
   disagreement (the engine only lets it see your rating once you've recorded it).
5. On a disagreement, you adjudicate (in the panel or the chat).
6. To cite: in the panel, record the decision, **Preview write**, then **Confirm &
   add to Zotero**. The write is previewed first and is **undoable**.

## What stays true

- You rate **before** the AI rating is visible — enforced by the engine and by
  every panel read endpoint, not by the LLM's good behaviour.
- No Zotero write happens without a preview and your explicit confirmation; every
  write is undoable.
- The panel is loopback-only and sends no telemetry. The chat LLM is your own
  client; CiteVahti adds no new data path.

See [`adr/0007-local-web-app-and-http-surface.md`](adr/0007-local-web-app-and-http-surface.md)
for the architecture and [`SAFETY_INVARIANTS.md`](SAFETY_INVARIANTS.md) for the guarantees.
