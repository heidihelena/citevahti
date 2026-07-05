---
name: citevahti-report
description: Use when packaging a completed CiteVahti audit for a journal, supervisor, or co-author — writing the methods-section paragraph that describes the claim-checking workflow, exporting the hash-chained audit trail, assembling an evidence appendix, or preparing a pre-submission integrity summary. Runs downstream of citevahti-dev, after the manuscript's claims have been rated and decided.
---

# CiteVahti report — package the audit for a human reader

`citevahti-dev` produces the machine record: the ledger of claims, states, and the
hash-chained audit trail. This skill turns that record into what a **person** reads —
a methods paragraph, an evidence appendix, and an inspectable audit trail a supervisor
or journal can check. It writes *about* the audit; it never re-runs it.

## Triggers

**Use when the researcher asks to:**
- write the methods text describing how citations were checked
- export or share the audit trail / integrity summary
- assemble an evidence appendix for submission or a supervisor
- get a pre-submission summary of claim states before they submit

**Do NOT use when:** claims are still unrated (run `citevahti-dev` first), or the ask is
to check a new claim, screen a bibliography (`citevahti-screen`), review someone else's
manuscript (`citevahti-review`), or draft body text (`citevahti-writing`).

## Prerequisite

The ledger exists and its claims are decided. Confirm with `citevahti status`; if claims
are still `[u]` untestable or `[r]` review-needed, stop and hand back to `citevahti-dev` —
a report over an unfinished audit misrepresents the work.

## What it produces (each from a real command; no number is invented)

1. **Methods paragraph** — `citevahti methods`. Plain prose describing the workflow
   actually used, plus the PRISMA-style discovery/flow disclosure: claims checked against
   cited sources through a blinded human rating with an advisory AI second opinion,
   disagreements adjudicated by the human, references written to Zotero as an audited step.
   States what was done, never that the result is certified.
2. **Integrity summary** — `citevahti report --format md`. The claim-state table:
   `[oo]` accepted, `[o]` needs-support, `[r]` review-needed, `[d]` decided (rejected),
   `[u]` untestable, with counts.
3. **Evidence appendix** — `citevahti evidence-export --format markdown`. Per claim: the
   sentence, the source cited, the support rating, and the human decision. The
   reviewer-facing companion to the ledger. (`--format csv` / `csl-json` also available.)
4. **Audit-trail check** — `citevahti verify-audit`. Recomputes the hash chain over
   `.citevahti/audit_log.jsonl` and reports whether it is intact (tamper-evident), so a
   supervisor or journal can confirm the record has not been altered.
5. *(Optional)* **Agreement numbers** — `citevahti agreement-report --metric cohen_kappa`
   for human↔AI agreement, when a methods section reports it.

## Workflow

```
citevahti status                              # confirm claims are decided
citevahti methods                             # the methods paragraph + PRISMA disclosure
citevahti report --format md                  # the claim-state integrity summary
citevahti evidence-export --format markdown   # the evidence appendix
citevahti verify-audit                        # confirm the hash-chained trail is intact
```

Present each artifact for the researcher to read and edit before they use it. The methods
paragraph is a draft they own, not final text.

> **Exit codes are a status signal, not an error.** `report` and `test` follow the
> CI convention — they still print the full report, but exit non-zero when claims need
> attention (`[o]` needs-support / `[r]` review-needed present). Read the output; don't
> treat a non-zero exit as a failed command.

## FORBIDDEN

These break the audit's honesty. Violating them is never justified.

- **NEVER** state or imply the manuscript is verified, correct, accurate, publication-ready,
  or of a certain quality. The report describes a *process*, not a verdict. Use *check /
  assess*, never *verify / prove / guarantee*.
- **NEVER** invent counts, hashes, or ratings — every number comes from the ledger via the
  commands above.
- **NEVER** upgrade a claim's state in the prose beyond its recorded state (`[oo]` accepted
  is an accepted **decision**, not proof the claim is true).
- **NEVER** describe the AI as having decided anything; it is a blinded advisory rater.

If any feels necessary: stop and surface the constraint to the researcher.

## Safety invariants

The report records whether cited sources support claims and who decided what. It does
**not** certify scientific truth, manuscript quality, or publication readiness — final
responsibility stays with the author, reviewer, editor, or institution. CiteVahti is not a
medical device and gives no clinical advice. See `docs/SAFETY_INVARIANTS.md` and
`docs/DISCLOSURE.md`; where a journal or supervisor is the reader, disclose the tool use and
the developer relationship.

## Worked example

1. Researcher: "Write the methods bit and give me something for the supervisor."
2. `citevahti status` → 41 claims, all decided (33 `[oo]`, 5 `[o]`, 3 `[d]`).
3. `citevahti methods` → a paragraph: claims checked against cited sources via a blinded
   human-first workflow with an advisory AI second opinion; 3 citations revised or removed;
   a hash-chained trail retained.
4. `citevahti evidence-export --format markdown` + `citevahti verify-audit` → the appendix,
   and confirmation the audit chain is intact.
5. Hand all three back for the researcher to read, edit, and decide whether to include.
