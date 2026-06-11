# CiteVahti Quickstart — from zero to your first claim-tested citation

*A product of [Vahtian](https://vahtian.com).* In ~10 minutes you'll take one
manuscript claim, find a supporting paper on PubMed, rate it, decide, and write an
**audited, undoable** reference into Zotero — `[oo] verified`.

> **What CiteVahti is (and isn't).** It records a documented **human → AI →
> adjudication** workflow. *You* are always the decider. It never writes silently,
> never invents citations, and never claims a paper supports a claim — it records
> *your* judgment, with provenance. Beta scope: **local-first and single-user**;
> literature lookups go to PubMed, OpenAlex, Semantic Scholar and Crossref, and writes
> (if connected) to your Zotero — no telemetry; your manuscript and ratings stay local.

---

## 0. Prerequisites
- **Zotero desktop** installed and **running** (CiteVahti reads your library locally, keyless).
- **Python 3.10+**.
- A contact **email for PubMed** (NCBI asks for one; never used for anything else).
- *Optional:* [Better BibTeX](https://retorque.re/zotero-better-bibtex/) for citekeys.

## 1. Install (on PyPI)
```bash
python -m venv .venv && source .venv/bin/activate
pip install "citevahti[keyring,mcp]"   # keyring = Zotero key in your OS keychain; mcp = chat surface
citevahti --help
```
<details><summary>or from source</summary>

```bash
git clone https://github.com/heidihelena/citevahti
cd citevahti && python -m venv .venv && source .venv/bin/activate
pip install -e ".[keyring,mcp]"
```
</details>

**VS Code extension** (the inline review surface — optional):
```bash
cd vscode-extension && npm install && npm run package
code --install-extension citevahti-vscode-0.15.0.vsix
```
Then set `citevahti.cliPath` to your `citevahti` binary (e.g. `.venv/bin/citevahti`).

## 2. One-time setup
```bash
citevahti init                                   # creates the .citevahti/ ledger
citevahti onboard --ncbi-email you@uni.edu \
                  --no-zotero-key --skip-validate # records your PubMed email (no secrets)
citevahti connect-zotero                          # ← the one-paste Zotero connect
```
`connect-zotero` opens Zotero's key page **pre-filled** (name + write permission).
Click **Save Key**, copy it, paste it back. CiteVahti validates it, learns your
userID automatically, and stores the key in your **OS keychain** — never in a file.
You should see `✓ Connected to Zotero as … (user …)`.

## 3. Start the workspace — two paths

CiteVahti has two co-primary surfaces (ADR-0007): a **chat client** via the MCP
server, and a **loopback side panel** where you record your blind rating. Pick the
path that matches how you want to work — both use the same `.citevahti/` ledger and
the human always rates first.

### Path A — chat-driven (recommended)

You don't launch a server yourself. Add one line to your chat client's MCP config;
the client spawns it and the panel + browser open for you:
```json
{ "mcpServers": { "citevahti": { "command": "citevahti", "args": ["start", "--root", "/path/to/project"] } } }
```
- **Claude Desktop / ChatGPT desktop:** add the block to the app's MCP config.
- **Claude Code:** `claude mcp add citevahti -- citevahti start --root /path/to/project`
- **Codex:** add the equivalent stdio server entry in `config.toml`.

Then run the **`run_claim_tests`** prompt in the chat — or just paste a manuscript
paragraph. The chat finds candidates and records the AI's second rating; **you rate
first in the panel**, the AI rating stays hidden until you do, and any Zotero write
is previewed → confirmed → **undoable**. That is the whole loop.

> **Don't run `citevahti start` in a terminal yourself for this path.** It's the
> command the client spawns. Run by hand it serves the MCP protocol on stdin — the
> terminal blocks, **no prompt returns**, and the panel stays **empty until a claim
> exists**. That's not a crash; it's a server waiting for a client. `Ctrl-C` stops
> it and returns your shell.

### Path B — hands-on (panel + CLI)

Prefer to drive every step by hand (or script it in CI)? Open **two terminals**.

Terminal 1 — bring up the panel; it stays running and occupies this terminal:
```bash
citevahti-panel --root /path/to/project     # http://127.0.0.1:8765, loopback only
```
Terminal 2 — run the loop on the CLI (sections 4–7 below). Reload the panel to see
each change.

> The panel opens **empty** — "No claims yet." That's expected until you add a
> claim in §4. Use `citevahti-panel` here, **not** `citevahti start`: `start` would
> grab stdin for the MCP protocol and never return your prompt.

## 4. Add a claim from your manuscript
```bash
citevahti claim-add \
  --text "Low-dose CT screening reduces lung-cancer mortality in high-risk populations." \
  --type effectiveness --location "Discussion ¶2"
# → claim recorded: claim-2026...-abcd1234   (copy this id)
```

## 5. Find candidate evidence (PubMed) and link it
```bash
citevahti literature-search --query "low-dose CT lung cancer screening mortality randomized" --question-id q1
# → intake batch  : intake-2026...-xxxx      (copy the batch id)

citevahti claim-link-candidates --claim-id <CLAIM_ID> --intake-batch-id <BATCH_ID>
citevahti candidate-list --claim-id <CLAIM_ID>
# → … cand=cand-...-yyyy                      (copy a candidate id)
```
> Finding a paper isn't citing it. The next step tests whether it actually
> **supports the claim**.

## 6. Review & decide — *you* are the decider

*(With the side panel up — from either path in §3 — you do this in the panel. The
two surfaces below are the same decision by hand — in the VS Code adapter, or fully
on the CLI.)*

### Option A — in VS Code
1. Open your manuscript (`.md`), run **CiteVahti: Verify claims** (Command Palette).
2. Each claim is highlighted by its state. Expand the claim, focus a candidate.
3. Rate support, then press the verdict: **`o o` accept → `[oo]`**, `o` caution, `r` review, `d` reject.
   *(The panel hides the AI's opinion until you rate; the ledger logs the order, so blinding is auditable.)*
4. On an accepted candidate, click **✓ Add to Zotero** → preview → confirm → done, with **Undo**.

### Option B — full CLI
```bash
citevahti claim-support-start --claim-id <CLAIM_ID> --candidate-id <CAND_ID>
# → claim-support rating started: cs-...-zzzz

citevahti claim-support-commit-human --rating-id <RATING_ID> --value directly_supports
citevahti claim-support-compare --rating-id <RATING_ID>

citevahti claim-decide --claim-id <CLAIM_ID> --candidate-id <CAND_ID> \
  --decision accept --reason "RCT directly evaluates the claim" --rating-id <RATING_ID>
# → decision_id : decision-...-wwww
#   → write it  : citevahti claim-commit --decision-id decision-...-wwww --commit
```
Then the **decision-gated write** (preview first, always):
```bash
citevahti claim-commit --decision-id <DECISION_ID>            # dry-run preview only
citevahti claim-commit --decision-id <DECISION_ID> --commit   # shows the preview, asks [y/N], then writes
# undo any time: citevahti txn-undo --transaction-id <TXN_ID>
```
`--commit` always shows the preview and asks before writing — never a silent write.
**Non-interactive (scripts/CI):** there's no prompt, so replay the token from the
preview. Run the preview as JSON, read its `confirm_token`, then commit with it:
```bash
TOKEN=$(citevahti claim-commit --decision-id <DECISION_ID> --json | python -c "import sys,json;print(json.load(sys.stdin)['confirm_token'])")
citevahti claim-commit --decision-id <DECISION_ID> --commit --confirm-token "$TOKEN"
```
A `--commit` without a token in a non-interactive shell refuses (`missing_confirm_token`)
— so nothing is ever written unseen.

## 7. The Citation-Integrity Report
```bash
citevahti claim-report                       # 4-state summary (exit ≠ 0 if any need attention)
citevahti claim-report --format md --output integrity.md   # the editor/supervisor report
```

## 8. Getting the references into your article or thesis

**CiteVahti's job ends with a vetted reference in your Zotero library** — checked against
the claim, deduped, audited. It does **not** insert live citations into your prose. So how
a citation reaches your final document depends on your writing tool:

- **Word / Google Docs (typical for a thesis):** your manuscript prose is plain text, so
  copy-pasting it carries no citations — CiteVahti never put any *in the prose*. But the
  **reference is already in your Zotero library**, vetted and deduped, so you cite it the
  normal way with the **Zotero Word/Docs plugin** ("Add/Edit Citation"). Nothing is lost —
  you *cite in Word*, you don't paste citations. (A plain text paste never carries live
  citations into Word; that's true of any tool.)
- **Markdown → Pandoc:** if you write citations as Better BibTeX keys in Pandoc form
  `[@citekey]`, those travel as plain text and **Pandoc `--citeproc`** (with a Better
  BibTeX `.bib`/CSL exported from Zotero) formats them into in-text citations + a
  bibliography automatically.

> **In short:** the Zotero references always persist; the *in-text citing* happens in your
> writing tool (Word + Zotero plugin, or Markdown + Pandoc) — not via copy-pasting prose.
> If you use `[@citekey]` markers, **pin your Better BibTeX citekeys** so they keep resolving.

---

## What just happened (the ledger)
```
claim → candidate → blinded support rating → your decision → guarded, undoable Zotero write → audit
```
Every step is recorded in `.citevahti/` with provenance and a **hash-chained audit
log** — so the whole workflow can be reported in a methods section. Verify it any
time: `citevahti verify-audit`.

## Safety, by design
- **You decide.** AI is a blinded, advisory second rater — never decisive, never silent.
- **No silent writes.** Every Zotero write is preview → confirm → commit, and undoable; duplicates fail closed by default. If a duplicate check can't be run, the write is refused unless you pass an explicit override — which is warned at preview and recorded on the committed transaction (`dedupe_unverified`).
- **Your key is yours.** Stored only in the OS keychain — never in config, logs, or settings. Reads need no key at all.

## Troubleshooting
| Symptom | Fix |
|---|---|
| "Zotero isn't connected" on write | Run `citevahti connect-zotero` (or the VS Code **Connect Zotero** command). |
| Reads fail / empty | Make sure **Zotero desktop is running** (the local API is keyless but needs the app open). |
| PubMed search rejected | Set your email: `citevahti onboard --ncbi-email you@uni.edu --no-zotero-key --skip-validate`. |
| "keyring … unavailable" | `pip install keyring`, or use the env key `CITEVAHTI_ZOTERO_WRITE_KEY` for a headless run. |
| Want the AI second opinion | Configure an AI model in `.citevahti/config.json` (`ai_provenance`); otherwise the human-only path above works fully. |
| Ran `citevahti start`; terminal has no prompt | Expected — `start` serves the MCP protocol on stdin (it's meant to be spawned by a chat client). `Ctrl-C` returns your shell. For hands-on use, run `citevahti-panel` instead (Path B). |
| Panel opens but is "static" / empty | "No claims yet" is the empty state — add a claim (§4), then reload the panel. Also check you started from your project folder, not `~` (the ledger is per-folder). |
| Shell stuck at `dquote>` on install | The install string lost its closing quote. `Ctrl-C`, then run `pip install "citevahti[mcp]"` with **both** quotes. |

Questions / issues: <https://github.com/heidihelena/citevahti/issues>
