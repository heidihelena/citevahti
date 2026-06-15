---
name: citevahti-writing
description: Use when a researcher wants to draft or extend manuscript text using verified citations, when they have reviewed evidence in MatchVahti or MatchVahti-Lite and marked places in a paper needing a reference, or when AI-assisted writing should draw only on claims that passed the human → AI → adjudication workflow
---

# CiteVahti Writing — AI-Assisted Drafting from Verified Evidence

## Overview

Coordinates the **MatchVahti → CiteVahti → AI writing** chain.
The researcher reviews evidence first, marks citation slots, CiteVahti
verifies and commits to Zotero, then AI drafts prose — drawing only on
claims the human has already adjudicated.

**The AI writes from verified evidence. It never invents citations.**

## The chain

```
MatchVahti-Lite (browser)     MatchVahti (app)
  tap citable sentence          blinded claim×paper loop
  [oo] closer-look flag         MatchResult in .citevahti/
  export .ris → Zotero          full-text claim checking
        ↓                               ↓
        └─────────────┬─────────────────┘
                      ↓
            CiteVahti (.citevahti/ ledger)
              claim verified → [oo] accepted → Zotero
                      ↓
            AI drafts prose from verified claims only
              human reviews → accepts / edits / rejects
                      ↓
            Manuscript with auditable citation trail
```

## Triggers

Use when:
- "Write a paragraph about X, I've verified the references"
- "Draft the discussion based on what I found in MatchVahti"
- "I marked [needs citation] — find and verify, then draft"
- "Expand this sentence with the evidence I cited"
- `[oo]` / `cite:closer-look` tags in Zotero mentioned
- Manuscript has `[REF]` / `<!-- cite: -->` / `(XXX et al.)` slots

Do NOT use: before researcher has reviewed evidence, to invent citations,
to bypass the human decision step.

## Workflow

**Before drafting — establish evidence state:**

| Researcher comes from | What to check | Ready when |
|---|---|---|
| MatchVahti-Lite | Zotero has `cite:abstract-only` items | Human has reviewed .ris import |
| MatchVahti (app) | `.citevahti/` ledger has MatchResult | Claim is `[oo]` or `[o]` |
| Neither | — | Run `citevahti-dev` first, return here |

Never draft from `[r]` review, `[d]` rejected, or unverified claims.

**Map citation slots → check ledger → draft → human review → insert citekeys.**

See `citevahti-writing-reference.md` for drafting rules, slot formats,
and the full MatchVahti-Lite vs MatchVahti comparison.

## cite:abstract-only — always flag in draft

MatchVahti-Lite exports carry this tag. Never silently drop it:

```
[@citekey] ⚠ abstract-only — verify against full text before submission
```

If `cite:closer-look` is also present: remind researcher to run
`vahtian_fulltext.py` → fetch PDF → step up to CiteVahti claim check.

## FORBIDDEN

- **NEVER draft before human has reviewed the evidence**
- **NEVER invent a citation or citekey**
- **NEVER use `[d]` rejected or `[r]` review claim as evidence**
- **NEVER strengthen claim beyond its support rating**
- **NEVER fill citation slot without a corresponding ledger entry**
- **NEVER present AI-drafted text as final without researcher review**

Unfilled slot with no verified claim: say so explicitly.
Offer `citevahti-dev` first, not a guess.

## Session handoff (always at end)

```
Drafted sections:    [list]
Citations used:      [citekeys + states]
Slots unfilled:      [list + reason]
Abstract-only flags: [list — needs full-text check before submission]
Caution claims [o]:  [list — needs researcher confirmation]
Next step:           [citevahti-dev / MatchVahti / full-text fetch / submission]
```

## Cross-skill references

**REQUIRED:** `citevahti-dev` — for claim verification before this skill runs
**REQUIRED REFERENCE:** `citevahti-writing-reference.md` — drafting rules and step detail
**BACKGROUND:** MatchVahti-Lite at vahtian.com/matchvahti-lite/
