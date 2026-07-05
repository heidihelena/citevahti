---
name: citevahti-review
description: Use when peer-reviewing or editing someone else's manuscript — checking whether each cited source supports the claim it is attached to, and producing a structured reviewer report of unsupported or overstated claims. Read-only, never writes to the author's Zotero and never rewrites their text. Uses the same blinded assessment as citevahti-dev.
---

# CiteVahti review — the reviewer's and editor's pass

`citevahti-dev` is for auditing your **own** manuscript, with write-back to your Zotero.
This skill is for auditing **someone else's** — as a peer reviewer or editor. It checks
whether each cited source supports the claim, and produces a structured report you fold
into your review. It changes nothing in the author's files.

## Triggers

**Use when the reviewer or editor asks to:**
- check whether the citations in a manuscript under review actually support its claims
- produce a reviewer report of unsupported or overstated claims
- assess a submission's evidence before recommending a decision

**Do NOT use when:** the manuscript is the user's own (`citevahti-dev`), or the ask is to
screen a plain reference list for retractions (`citevahti-screen`).

## What makes it different from citevahti-dev

- **Read-only, and library-free.** You review from the submission text, not the author's
  Zotero. The core command is `citevahti claim-verify --claim "<claim>" --text-file
  <source-excerpt>` — it checks a claim against **provided** text, offline, with no Zotero
  and no network. It writes nothing.
- **Assess, don't author.** You are judging whether the source supports the claim, not
  fixing the wording. Suggested wording goes to the author as a comment, never as an edit.

There is no single `citevahti review <file>` command — the review is a read-only pass of
`claim-verify` (and `claim-check`, if you happen to have the sources in a library) over the
submission's cited claims, assembled into a report.

## Workflow

```
# per cited claim, against the passage the author quotes/cites:
citevahti claim-verify --claim "<the manuscript claim>" --text-file <source-passage>.txt
```

For each cited claim, assess support (blinded human first, advisory AI second) and draft a
report entry: the claim, the source cited, the support assessment, and a neutral query you
can raise with the author.

## Output — a reviewer report

Ranked by how far the source falls short of the claim. Each entry:
- the manuscript claim and the source cited for it
- the support assessment, using CiteVahti's frozen vocabulary —
  **supports / contrasts / unclear / not_relevant** (never an invented scale)
- a suggested, neutral reviewer comment ("The cited source studied population X; the claim
  generalizes to Y — please reconcile or qualify.")

## Claim states

Assessed claims are marked `[o]` needs-support or `[r]` review-needed in a local,
reviewer-side ledger. Nothing is `[oo]` accepted or `[d]` written — you are not the author
and make no decision on their behalf.

## FORBIDDEN

- **NEVER** state that a claim is false — only whether the *cited source supports it*.
  Truth is not what this checks. Use *check / assess*, never *verify / prove*.
- **NEVER** decide the manuscript's fate; the report informs the human reviewer, who
  decides and writes their own review.
- **NEVER** write to the author's Zotero, edit their text, or contact the author or journal.
- **NEVER** present the AI's assessment as the reviewer's opinion; it is a blinded advisory
  input the reviewer weighs.
- **Disclose.** Many journals require reviewers to disclose AI tool use. Remind the reviewer
  to check the journal's policy and disclose accordingly.

If any feels necessary: stop and surface the constraint to the reviewer.

## Safety invariants

The review report records whether cited sources support claims. It does **not** certify
truth, judge quality, or recommend a decision — the reviewer or editor decides, on their own
responsibility, and discloses tool use per journal policy. CiteVahti is not a medical device
and gives no clinical advice. See `docs/SAFETY_INVARIANTS.md` and `docs/DISCLOSURE.md`.

## Worked example

1. Reviewer: "Check the citations in this submission I'm reviewing."
2. For each cited claim, `citevahti claim-verify --claim "…" --text-file passage.txt` →
   28 cited claims assessed, read-only, no Zotero touched.
3. Report: 3 does-not-support, 4 partial, each with a neutral comment to raise.
4. The reviewer weighs them, writes their own review, and discloses the tool use if the
   journal requires it. CiteVahti wrote nothing.
