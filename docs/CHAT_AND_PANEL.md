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

## 3. Start the side panel (the inline reviewer)

```bash
citevahti-panel --root /path/to/project        # http://127.0.0.1:8765, loopback only
```

The panel is the **inline reviewer**: it shows your manuscript with each claim
highlighted in place, and an action-first card that walks one step at a time —
**Rate → Reveal → Decide → Write**. Open `http://127.0.0.1:8765` next to your chat.
(`--port` changes the port; it binds to `127.0.0.1` and must not be exposed.)

- **Never lands blank.** If you omit `--root`, the panel uses `$CITEVAHTI_ROOT`,
  the current folder's ledger, or the **last-used root** — instead of an empty
  `~/.citevahti`. If the active ledger has no claims, it shows a first-run screen
  that lists other ledgers it found (with claim counts) and a one-click switch.
- **Bind your manuscripts folder** (top of the editor) so claims render inside the
  real prose. Until you do, the document is reconstructed from the claim text, so
  it is never empty.
- **Find evidence in the panel.** Each claim's card has a search box — search
  **PubMed** or your **Zotero library**, then click **Link** on a result to attach it
  as a candidate. You no longer have to switch to the chat to add evidence. (Staging
  only; you still rate each candidate.)
- **Revise the manuscript in the panel.** A *Needs review* verdict gives you an
  editable wording box; *Reject* strikes the claim. Either writes to your `.md`
  behind preview → confirm → undo (the file is backed up first).
- **Connect inline.** The header shows Zotero / PubMed chips; click to connect when
  a step needs them. Keys are validated and stored in your OS keychain by the
  engine — they never round-trip back to the browser.
- **Connect Zotero by OAuth or by key.** At the write step you can **Connect with
  Zotero (OAuth)** — a one-click handshake that opens Zotero, you authorize, and the
  key is stored for you (no copy/paste) — or paste a write-enabled API key. Both end
  in the same validated, keychain-stored, write-enabled state.

### One-time OAuth app setup (optional)

The OAuth button needs a registered CiteVahti OAuth *application* (this is set up
once, not per user). Register at <https://www.zotero.org/oauth/apps> (callback URL
`http://127.0.0.1:8765/oauth/zotero/callback`), then export the client credentials
before launching the panel:

```bash
export CITEVAHTI_ZOTERO_OAUTH_CLIENT_KEY=...        # the app's Client Key
export CITEVAHTI_ZOTERO_OAUTH_CLIENT_SECRET=...     # the app's Client Secret (never committed)
```

Until those are set, the OAuth button explains the setup and you can still paste a
key. Zotero's passkey login (2026) only changes how you sign in to authorize — the
API-key mechanism CiteVahti uses is unchanged.

**Callback URL.** By default the handshake uses the **loopback** callback
`http://127.0.0.1:8765/oauth/zotero/callback` — most private, nothing leaves your
machine. If your Zotero app must register an HTTPS domain instead, set
`CITEVAHTI_ZOTERO_OAUTH_CALLBACK=https://vahtian.com/citevahti/auth/zotero/callback`
and host that path as a **thin client-side bounce** that redirects the incoming
`oauth_token` and `oauth_verifier` to the loopback callback above. The token
exchange and key storage still happen locally — the hosted page never sees the API
key, keeping the connect flow local-first.

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
7. To fix wording instead: a *Needs review* or *Reject* verdict offers a document
   edit — apply the revision (or strike the claim) directly in your `.md`. The panel
   shows the diff, **backs up the file before writing**, and the edit is **undoable**
   byte-for-byte. Nothing is written to a manuscript without your confirm.

## What stays true

- You rate **before** the AI rating is visible — enforced by the engine and by
  every panel read endpoint, not by the LLM's good behaviour.
- No Zotero write happens without a preview and your explicit confirmation; every
  write is undoable.
- No manuscript `.md` edit happens without a preview and your confirmation; the file
  is backed up first and every edit is undoable. Backups live in
  `<root>/.citevahti/manuscript_backups`; CiteVahti keeps the **10 most recent per
  manuscript** and prunes older ones after each new backup is written — the newest
  valid backup is never deleted. Set `CITEVAHTI_BACKUP_RETENTION_COUNT` to change the
  cap (default `10`; a non-positive or invalid value falls back to `10`).
  Connecting Zotero/PubMed stores keys in your OS keychain via the engine — secret
  values are never returned to the panel.
- The panel is loopback-only and sends no telemetry. The chat LLM is your own
  client; CiteVahti adds no new data path.

See [`adr/0007-local-web-app-and-http-surface.md`](adr/0007-local-web-app-and-http-surface.md)
for the architecture and [`SAFETY_INVARIANTS.md`](SAFETY_INVARIANTS.md) for the guarantees.
