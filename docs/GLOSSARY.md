# Glossary

CiteVahti's vocabulary, with the clinical distinction between a **claim** (the
testable unit the product is built around) and a **statement** (the broader
category of manuscript text that may need support). These are *not* synonyms — in
clinical writing they mean different things, and CiteVahti keeps them distinct.

For the full workflow these terms sit inside, see
[`adr/0001-citation-integrity-architecture.md`](adr/0001-citation-integrity-architecture.md)
and [`METHODS.md`](METHODS.md).

## The first-class unit

**Claim** — a testable scientific assertion in a manuscript: the unit CiteVahti
"runs a unit test" on. The claim is the first-class object of the ledger and of
the CLI (`claim-add`, `claim-check`, `claim-support`, `claim-decide`). Every
candidate, rating, decision, and write hangs off a claim.

## Statement vocabulary

**Statement** — a sentence or passage in a manuscript that may need support from
the study results, cited literature, or both. Broader than a claim: not every
statement is a testable claim, but every claim is a statement that has been made
precise enough to test.

**Evidence-linked statement** — a statement whose wording depends on empirical,
clinical, mechanistic, methodological, or prior-literature support. These are the
statements worth auditing; purely structural or rhetorical sentences are not.

**Candidate citation** — a possible source for a statement. (In the ledger, a
candidate paper linked to a claim.) Finding a candidate is not the same as citing
it — its fit must still be rated.

**Statement–citation match** — the relationship between a manuscript statement and
a cited source: whether, and how well, the source supports the statement.

**Statement audit** — a structured check of whether a statement is appropriately
supported. CiteVahti records the audit (the blinded human → AI → adjudication
trail); it does not decide support on the author's behalf.

**Support source** — the basis for the statement: own results, cited literature,
both, or unresolved.

## How this maps to the ledger

The audited path CiteVahti records is:

```
claim → candidate citation → blinded claim-support rating
  → human-owned final decision → decision-gated, undoable Zotero write → audit
```

A **statement** is what an author writes; a **claim** is a statement made testable;
a **statement audit** is the recorded check that a claim's candidate citations
actually support it. The human is always the decider — the AI is a blinded,
advisory second rater only.
