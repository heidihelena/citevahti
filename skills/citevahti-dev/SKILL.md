---
name: citevahti-dev
description: Use when verifying manuscript claims against evidence, checking whether a citation actually supports what it is cited for, adding audited references to Zotero, generating a citation-integrity report, or when a researcher mentions claims, citations, PubMed, Zotero, PRISMA, blinded rating, or peer review of evidence
---

# CiteVahti — Citation Integrity for Manuscripts

## Overview

CiteVahti runs **unit tests on manuscript claims**: each claim is a test case,
each candidate paper is an assertion. It records a **human → AI → adjudication**
decision chain with a hash-chained audit log.

The human is always the decider. The AI is a blinded advisory second rater only.
Nothing is written to Zotero without explicit preview → confirm → commit.

## Three doors — same product

| Who says this | What they mean |
|---|---|
| "Run unit tests on my manuscript" | agents / technical users |
| "Check every claim before I cite it" | researchers |
| "Create an auditable claim-evidence trail" | journals / institutions |

## Triggers

Use when:
- "Check if this citation supports the claim"
- "Verify my references" / "citation integrity"
- "Add to Zotero" after evidence review
- "PRISMA" / "systematic review" / "evidence synthesis"
- "Citation-integrity report" for manuscript methods
- `[oo]` / `[o]` / `[r]` / `[d]` claim states mentioned
- "Blinded rating" / "dual rater" for citations
- Desk rejection for citation quality

Do NOT use for: general PubMed search without a manuscript claim, Zotero
library management unrelated to claim verification, screening / inclusion decisions.

## Setup paths

### Path A — FullVahti / Claude Desktop (no terminal)

Download `citevahti.mcpb` from the latest release, double-click, pick project
folder. Bundled runtime — no Python needed. Run `run_claim_tests` in chat.
**Recommended for non-technical researchers.**

### Path B — Claude Code (MCP stdio)

```bash
pip install "citevahti[keyring,mcp]"
citevahti init
citevahti onboard --ncbi-email you@uni.edu --no-zotero-key --skip-validate
citevahti connect-zotero
claude mcp add citevahti -- citevahti start --root /path/to/project
```

Then run `run_claim_tests` prompt in chat.

**`citevahti start` blocks in terminal — that is correct.** It serves MCP stdio
for the chat client. For hands-on terminal use, run `citevahti-panel` instead.

### Path C — VS Code inline

Install `.vsix`, set `citevahti.cliPath`, run **CiteVahti: Verify claims**
from Command Palette.

## Core workflow

```
claim-add  →  literature-search  →  claim-link-candidates
    ↓
[HUMAN rates first — AI rating hidden until commit]
    ↓
claim-support-commit-human  →  claim-support-compare
    ↓
claim-decide  →  claim-commit (preview → [y/N] → write)
    ↓
claim-report  /  agreement-report
```

See `citevahti-commands.md` for full command reference with all flags.

## Claim states

| State | Meaning |
|---|---|
| `[oo]` accepted | Human + AI concordant, accepted |
| `[o]` caution | Accepted with reservation |
| `[r]` review | Needs adjudication |
| `[d]` rejected | Does not support claim |
| `[u]` untestable | Outside indexed literature |

Mark untestable claims explicitly — never leave as "needs support":
```
citevahti claim-untestable <claim-id> --reason "monograph, not indexed"
```

## FORBIDDEN operations — hard gates

These are never justified. Violating them breaks the audit chain:

- **NEVER write to Zotero** without `--commit` + user `[y/N]`
- **NEVER invent a citekey** — citekeys from Better BibTeX only
- **NEVER set `final_value` from AI rating** — human/panel only
- **NEVER propagate AI rating silently** — discordance routes to human
- **NEVER fabricate PubMed candidates** — search only
- **NEVER claim a paper supports a claim** — record what the human decided

If any feels necessary: stop, surface the constraint to the user.

## FullVahti / .mcpb integration

`.mcpb` bundles the Python runtime. For Claude Desktop:
1. User double-clicks `.mcpb`, picks project folder once
2. Run `run_claim_tests` in Claude Desktop chat
3. Agent drives claim loop; panel opens for human rating at the right moment
4. Every write is previewed — agent proposes, human confirms

For Claude Code: use Path B above. The MCP server is the same; the shell is
the entry point instead of the Desktop app.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Terminal blocks after `citevahti start` | Expected — MCP server. Use `citevahti-panel` for hands-on. Ctrl-C returns shell. |
| Panel shows "No claims yet" | Add a claim first, then reload. |
| "Zotero isn't connected" | Run `citevahti connect-zotero` |
| PubMed search rejected | `citevahti onboard --ncbi-email you@uni.edu` |
| "keyring unavailable" | `pip install keyring` or use env `CITEVAHTI_ZOTERO_WRITE_KEY` |
| Duplicate write refused | Expected — dedupe fails closed. `--allow-duplicate` only if verified. |

## Worked example — check one claim end to end

A researcher pastes: *"Adjuvant immunotherapy improves disease-free survival in
resected stage II–III NSCLC [needs citation]."*

```
# 1. capture the claim
citevahti claim-add "Adjuvant immunotherapy improves disease-free survival in resected stage II–III NSCLC"
#   → claim_id: claim-20260704-...

# 2. find candidate papers (PubMed; abstracts included for the blinded rater)
citevahti literature-search --query "adjuvant immunotherapy resected NSCLC disease-free survival" --max-results 5
citevahti claim-link-candidates <claim-id>        # stage the candidates as evidence

# 3. the HUMAN rates first — the AI rating stays sealed until this is committed
citevahti claim-support-commit-human <claim-id> --rating supports --fit "population + outcome match"
citevahti claim-support-compare <claim-id>        # now the AI second opinion is revealed

# 4. human-owned decision, then a previewed, undoable Zotero write
citevahti claim-decide <claim-id> --final accept
citevahti claim-commit <claim-id> --commit         # prints the write, asks [y/N], then writes + audits

# 5. the record
citevahti claim-report        # per-claim states; agreement-report for human↔AI κ
```

The same loop runs conversationally through the `run_claim_tests` MCP prompt (the
agent may pre-screen and record its rating first — you never see it until yours is in)
and visually in the loopback review panel.

## Safety invariants (enforced in code; full offline test suite, 1000+ tests)

- Zotero local API read-only / GET-only
- AI rating advisory only — never sets `final_value`
- All mutations hash-chain audited in `.citevahti/audit_log.jsonl`
- Dedupe fails closed
- Zotero key in OS keychain only — never in config or logs

**REQUIRED REFERENCE:** `docs/SAFETY_INVARIANTS.md` — full invariant list
and test coverage mapping.
