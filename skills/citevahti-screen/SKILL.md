---
name: citevahti-screen
description: Use when checking an existing reference list or bibliography before submission — flagging retracted papers and expressions of concern, spotting citations whose cited source does not support the claim, and producing a pre-submission triage list. Screens the bibliography you already have, before a reviewer does. Complements citevahti-dev, which checks claims one at a time.
---

# CiteVahti screen — sweep the reference list before a reviewer does

`citevahti-dev` checks claims one at a time as you write. This skill sweeps the
**references you already have** and flags what a reviewer would catch — retractions,
expressions of concern, and citations whose source does not support the sentence. It is a
read-only worklist: nothing is fixed, removed, or written back.

## Triggers

**Use when the researcher asks to:**
- check a manuscript or reference list for retracted papers before submitting
- screen a bibliography for problems in one sweep
- get a triage list of citations that need a second look

**Do NOT use when:** the ask is to check a single new claim (`citevahti-dev`), package a
finished audit (`citevahti-report`), or review someone else's manuscript
(`citevahti-review`).

## What it checks (each a real command; nothing is auto-fixed)

- **The citation suite** — `citevahti test --online`. Runs the "unit tests for citations"
  over the ledger and, with `--online`, also checks each cited reference is real and **not
  retracted**. This is the single closest thing to "screen the whole manuscript."
- **Retraction status** — `citevahti retraction-scan` (bare = scan every staged reference;
  or `--citekey` / `--doi` / `--pmid` for one). Cross-checks against retraction and
  expression-of-concern notices. A clean result is "no known retraction," **not** a
  warranty that every one was caught.
- **Claim–source support** — `citevahti claim-check --claim "<sentence>"` (deterministic,
  read-only, against your Zotero library). Flags citations whose source likely does not
  support the sentence, for the human to check.
- **Triage worklist** — `citevahti triage`. Surfaces what needs attention, worst first,
  each with a plain reason and next action.

There is no single `citevahti screen <file>` command — screening is this read-only sweep
composed from the commands above, ending in a triage list.

## Output — a triage list, ranked by severity

```
citevahti test --online       # citation suite incl. real-and-not-retracted checks
citevahti retraction-scan     # retraction / expression-of-concern sweep
citevahti triage              # the worst-first worklist to hand back
```

Retractions first, then likely claim–source mismatches, then list hygiene (duplicates,
in-text citations missing from the list). Each row names the reference, what was flagged,
and the sentence to check. It is a worklist for the human — nothing is auto-fixed.

## Claim states

A flagged citation surfaces as `[r]` review-needed; it becomes `[oo]` accepted,
`[o]` needs-support, or `[d]` decided only through `citevahti-dev`, after the human rates.

## FORBIDDEN

- **NEVER** remove, rewrite, or "fix" a citation automatically — screening produces a
  worklist, the human decides.
- **NEVER** state a paper is sound or a citation is correct — the tool flags problems, it
  does not clear a reference. Use *check / assess*, never *verify / prove*.
- **NEVER** claim to catch every retraction or every mismatch; report only what was found.
- **NEVER** write to Zotero or the manuscript.

If any feels necessary: stop and surface the constraint to the researcher.

## Safety invariants

Screening flags citations to check; it records support assessments and known-retraction
matches, and it does **not** certify that the remaining references are correct or that the
manuscript is sound. The human is the decider. CiteVahti is not a medical device and gives
no clinical advice. See `docs/SAFETY_INVARIANTS.md`.

## Worked example

1. Researcher: "Check my reference list before I submit."
2. `citevahti test --online` → citation suite run; `citevahti retraction-scan` → all staged
   references checked.
3. Result via `citevahti triage`: 1 retraction (flag to remove or replace), 4 likely
   claim–source mismatches (`[r]`, sentences listed), 2 duplicates.
4. Hand the triage list back. The researcher decides each; checking the mismatches runs
   through `citevahti-dev`.
