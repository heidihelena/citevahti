# CiteVahti Quickstart — from zero to your first verified citation

*A product of [Vahtian](https://vahtian.com).* In ~10 minutes you'll take one
manuscript claim, find a supporting paper on PubMed, rate it, decide, and write an
**audited, undoable** reference into Zotero — `[oo] verified`.

> **What CiteVahti is (and isn't).** It records a documented **human → AI →
> adjudication** workflow. *You* are always the decider. It never writes silently,
> never invents citations, and never claims a paper supports a claim — it records
> *your* judgment, with provenance. Beta scope: **local-first, single-user,
> PubMed-only.**

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
code --install-extension citevahti-0.12.0.vsix
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

## 3. Start the workspace — `citevahti start`
This is the recommended path: one command opens the side panel + browser and
serves the chat tools.
```bash
citevahti start          # launches the panel + browser, then serves MCP (Ctrl-C stops)
```
Put the **same** command in your chat client, so one config line gives you
everything:
```json
{ "mcpServers": { "citevahti": { "command": "citevahti", "args": ["start"] } } }
```
Then in the chat (Claude Desktop / Claude Code / ChatGPT / Codex) run the
**`run_claim_tests`** prompt — or just paste a manuscript paragraph. The chat finds
candidates and records the AI's second rating; **you rate first in the panel**, the
AI rating stays hidden until you do, and any Zotero write is previewed → confirmed →
**undoable**. That is the whole loop.

> Prefer to drive every step by hand (or script it in CI)? Sections 4–7 are the
> same loop spelled out on the CLI — the manual path under `citevahti start`.

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

*(With `citevahti start` you do this in the side panel. The two surfaces below are
the same decision by hand — in the VS Code adapter, or fully on the CLI.)*

### Option A — in VS Code
1. Open your manuscript (`.md`), run **CiteVahti: Verify claims** (Command Palette).
2. Each claim is highlighted by its state. Expand the claim, focus a candidate.
3. Rate support, then press the verdict: **`o o` accept → `[oo]`**, `o` caution, `r` review, `d` reject.
   *(The AI's opinion stays hidden until you rate — blinding is real.)*
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
- **No silent writes.** Every Zotero write is preview → confirm → commit, and undoable; duplicates fail closed.
- **Your key is yours.** Stored only in the OS keychain — never in config, logs, or settings. Reads need no key at all.

## Troubleshooting
| Symptom | Fix |
|---|---|
| "Zotero isn't connected" on write | Run `citevahti connect-zotero` (or the VS Code **Connect Zotero** command). |
| Reads fail / empty | Make sure **Zotero desktop is running** (the local API is keyless but needs the app open). |
| PubMed search rejected | Set your email: `citevahti onboard --ncbi-email you@uni.edu --no-zotero-key --skip-validate`. |
| "keyring … unavailable" | `pip install keyring`, or use the env key `CITEVAHTI_ZOTERO_WRITE_KEY` for a headless run. |
| Want the AI second opinion | Configure an AI model in `.citevahti/config.json` (`ai_provenance`); otherwise the human-only path above works fully. |

Questions / issues: <https://github.com/heidihelena/citevahti/issues>
