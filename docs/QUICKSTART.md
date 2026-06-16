# CiteVahti Quickstart — check your first citation in ~10 minutes

*A product of [Vahtian](https://vahtian.com).* This guide assumes **no prior terminal
experience**. You'll take one sentence from your manuscript, find a paper that should
support it, judge whether it really does, and save an **audited, undoable** reference into
Zotero. Every command is something you **copy and paste** — nothing to memorise.

> **What CiteVahti is (and isn't).** It records a documented **human → AI → adjudication**
> workflow. *You* are always the decider. It never writes silently, never invents
> citations, and never claims a paper supports a claim — it records *your* judgment, with
> provenance. Beta scope: **local-first and single-user**; literature lookups go to PubMed,
> OpenAlex, Semantic Scholar and Crossref, and writes (if you connect Zotero) go to your
> Zotero — no telemetry; your manuscript and ratings never leave your machine.

---

## The easiest path: no terminal at all (Claude Desktop)

If you use **Claude Desktop**, you don't need a terminal:

1. Download **`citevahti.mcpb`** from the [latest release](https://github.com/heidihelena/citevahti/releases/latest).
2. Double-click it. Claude Desktop installs it and asks once for a folder to keep your work in.
3. In the chat, type **`run_claim_tests`** and paste a paragraph of your manuscript.

The assistant finds candidate papers and opens the rating panel in your browser when it's
your turn to rate. The runtime is bundled — no Python, no setup. **You can stop reading here.**

The rest of this guide is the **terminal route** (more control, works with any chat client).

---

## 1. Install it

You'll use the **Terminal** app (on macOS: press `⌘ Space`, type "Terminal", hit Enter; on
Windows: open "PowerShell"; on Linux: your terminal). **Copy the block below and paste it
in**, then press Enter:

```bash
python -m venv .venv && source .venv/bin/activate
pip install "citevahti[keyring,mcp]"
```

(That makes a private workspace and installs CiteVahti into it. `keyring` keeps your Zotero
key in your computer's secure keychain; `mcp` lets a chat assistant connect.)

> On Windows PowerShell the middle step is `.venv\Scripts\Activate.ps1` instead of
> `source .venv/bin/activate`. Everything else is identical.

## 2. Open CiteVahti

Make sure **Zotero is open** (CiteVahti reads your library from the running Zotero app).
Then **copy this and paste it into your terminal:**

```bash
citevahti run
```

That one command does everything: it creates your project, checks what's set up, prints the
next step, and **opens the review panel in your browser**. A banner at the top of the panel
always tells you the single next thing to do — you're never lost.

- Came back the next day? Run **`citevahti resume`** — it reopens the panel right where you
  left off.
- Not sure something's set up? Run **`citevahti doctor`** — it explains, in plain language,
  what's ready and what to fix.

## 3. Connect your sources (in the panel)

On first run the panel shows two buttons:

- **Connect Zotero** — needed only to *save* references back to Zotero. Click it; CiteVahti
  opens Zotero's key page with everything pre-filled. Click **Save Key**, copy the key, and
  paste it back. (Your key is stored in your computer's keychain — never in a file.)
- **Connect PubMed** — enter a contact email (PubMed asks every tool for one; it's used only
  to talk to PubMed).

You can rate and decide without Zotero connected — you only need it for the final "save the
citation" step.

## 4. Do the loop — in the panel

Paste a paragraph of your manuscript into the panel's box (or, in your chat client, run the
**`run_claim_tests`** prompt). CiteVahti highlights the claim-like sentences. Click one, and
the card on the right walks you through four steps, following the banner's prompts:

1. **Rate** — read the candidate paper and record *your* judgment of whether it supports the
   claim. You go first.
2. **Reveal** — only now does the AI's independent second opinion appear. If you disagree,
   you adjudicate; the AI never decides.
3. **Decide** — press the verdict: **Accept**, **Accept with caution**, **Needs review**, or
   **Reject**.
4. **Write** — for an accepted claim, click **✓ Add to Zotero** → preview → confirm → done,
   with **Undo** if you change your mind. Nothing is ever written without your confirmation.

When every claim is handled, the banner offers **Export report**. You can also download it
any time from the header — see §6.

<details><summary><b>Prefer to drive every step from the terminal?</b> (power users / scripting)</summary>

The panel is the recommended surface. But the whole loop is also available as commands —
each one prints an id you paste into the next. **Copy/paste, replacing the `<…>` parts:**

```bash
# add a claim
citevahti claim-add --text "Low-dose CT screening reduces lung-cancer mortality." --type effectiveness
# → claim recorded: claim-…   (copy this id)

# find candidate papers on PubMed and link them to the claim
citevahti literature-search --query "low-dose CT lung cancer screening mortality randomized" --question-id q1
# → intake batch: intake-…    (copy this id)
citevahti claim-link-candidates --claim-id <CLAIM_ID> --intake-batch-id <BATCH_ID>
citevahti candidate-list --claim-id <CLAIM_ID>          # → cand-…  (copy a candidate id)

# rate (you first), then decide
citevahti claim-support-start --claim-id <CLAIM_ID> --candidate-id <CAND_ID>     # → cs-… rating id
citevahti claim-support-commit-human --rating-id <RATING_ID> --value directly_supports
citevahti claim-support-compare --rating-id <RATING_ID>
citevahti claim-decide --claim-id <CLAIM_ID> --candidate-id <CAND_ID> \
  --decision accept --reason "RCT directly evaluates the claim" --rating-id <RATING_ID>
# → decision-…  (copy this id)

# save to Zotero — always previews first, then asks before writing
citevahti claim-commit --decision-id <DECISION_ID>            # preview only
citevahti claim-commit --decision-id <DECISION_ID> --commit   # shows preview, asks [y/N], writes
# undo any time:
citevahti txn-undo --transaction-id <TXN_ID>
```

For scripts/CI (no prompt available), replay the preview's token:
```bash
TOKEN=$(citevahti claim-commit --decision-id <DECISION_ID> --json | python -c "import sys,json;print(json.load(sys.stdin)['confirm_token'])")
citevahti claim-commit --decision-id <DECISION_ID> --commit --confirm-token "$TOKEN"
```

> **Citing a book, chapter, or report?** Sources outside the indexed literature can't be
> auto-checked — that's a scope limit, not a failed claim. Mark it:
> `citevahti claim-untestable <claim-id> --reason "monograph, not indexed"` and the report
> shows `[u] untestable` instead of "needs support".
</details>

## 5. Get the references into your thesis or paper

CiteVahti's job ends with a **vetted reference sitting in your Zotero library** — checked
against the claim, deduped, audited. It does *not* type citations into your prose. How a
citation reaches your document depends on your writing tool:

- **Word / Google Docs:** the reference is already in Zotero, so cite it the normal way with
  the **Zotero Word/Docs plugin** ("Add/Edit Citation"). (Pasting prose never carries live
  citations in any tool — you cite *in* Word.)
- **Markdown → Pandoc:** write `[@citekey]` markers; **Pandoc `--citeproc`** with a Better
  BibTeX `.bib` from Zotero formats them automatically. Pin your Better BibTeX citekeys so
  they keep resolving.

Want the **actual PDFs** beside your vetted references? [**FullVahti**](https://github.com/heidihelena/fullvahti)
is a companion Zotero plugin (two clicks, no terminal) that fetches free, legal open-access
full text from Unpaywall and PubMed Central into the same library, and honestly reports what
isn't available.

## 6. Your proof of work — the timestamped report

Click **⎙ Report** in the panel header any time (or run `citevahti claim-report --format md
--output integrity.md`). You get a Markdown **Citation-Integrity Report** that records:

- **when** it was generated, and **how many** claims were tested in each state;
- an **Integrity** line carrying the hash-chained **audit head** and whether the chain is
  intact — a tamper-evident record that *this review work was done, in this order, by you*.

In an age of AI writing, that timestamped, audit-anchored report is how you show the
verification was your own work — not a black box. (`citevahti agreement-report` and
[REPORTING.md](REPORTING.md) add the method-transparency paragraph for a paper.)

---

## What just happened (the ledger)
```
claim → candidate → blinded support rating → your decision → guarded, undoable Zotero write → audit
```
Every step is recorded in your project's `.citevahti/` folder with provenance and a
**hash-chained audit log**, so the whole workflow is reportable. Verify it any time with
`citevahti verify-audit`.

## Safety, by design
- **You decide.** AI is a blinded, advisory second rater — never decisive, never silent.
- **No silent writes.** Every Zotero write is preview → confirm → commit, and undoable;
  duplicates fail closed.
- **Your key is yours.** Stored only in your OS keychain — never in config, logs, or
  settings. Reading your library needs no key at all.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Not sure what's set up | Run **`citevahti doctor`** — it lists what's ready and the next step in plain language. |
| "Zotero isn't connected" on write | Click **Connect Zotero** in the panel (or run `citevahti connect-zotero`). |
| Reads fail / library empty | Make sure the **Zotero desktop app is open** (the local connection needs it running). |
| PubMed search rejected | Set your email: `citevahti onboard --ncbi-email you@uni.edu --no-zotero-key --skip-validate`. |
| The panel says "No claims yet" | Expected until you add a claim — paste a paragraph in the panel, or run the `run_claim_tests` prompt in your chat client. |
| "keyring … unavailable" | `pip install keyring`, or set `CITEVAHTI_ZOTERO_WRITE_KEY` for a headless run. |
| Want the AI second opinion | Configure an AI model in `.citevahti/config.json` (`ai_provenance`); the human-only path works fully without it. |
