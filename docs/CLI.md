# CLI reference

All commands take a global `--root <dir>` (the project containing `.citevahti/`;
defaults to the current directory). Commands print **ids, counts, statuses, and
file paths** — never private library content (no note bodies, source passages,
abstracts, or titles) unless an explicit `--show-*` flag is given. All write
commands default to **dry-run**.

```bash
citevahti --root . <command> [options]
```

## State & probe

| Command | Purpose |
|---|---|
| `init` | Create the `.citevahti/` state layer (config, dirs, genesis audit). |
| `probe` | Probe Zotero `/api/`, BBT `api.ready`, CAYW `probe=1`; reports versions + remediation. |
| `status` | **Connection & Capabilities** (read-only): live Zotero/BBT connection + versions, PubMed email + secret *state* (never values), and the configured write backend's **real** supported vs unsupported operations + permissions. |
| `connect-zotero` | `--name`, `--key`, `--no-open` — **guided one-paste Zotero connection** (ADR-0005): opens the pre-filled new-key page, takes the pasted key, validates it, learns the userID automatically, stores the key in the OS keychain, and enables guarded web-API write-back. Reads stay keyless. |
| `verify-audit` | Verify the hash-chained audit log is intact. |

## Citation integrity

| Command | Key options |
|---|---|
| `bib-sync` | `--target` (repeatable), `--output-dir`, `--format bibtex\|biblatex\|csl-json`, `--fail-on-orphans`, `--library` |

## Claims (ADR-0001 — the spine)

| Command | Key options |
|---|---|
| `claim-add` | `--text`, `--type <claim_type>`, `--location`, `--manuscript-id`, `--extracted-by human\|ai\|imported`, `--extraction-model` (required when `--extracted-by ai`) |
| `claim-list` | `--show-text` |
| `claim-untestable` | `<claim-id>` + `--reason "…"` or `--clear` — mark the cited source as out of indexed scope (book/chapter/grey lit); reported `[u] untestable`, never "needs attention" |
| `claim-propose-revision` | `--claim-id`, `--text`, `--extracted-by`, `--extraction-model` — attach a pending rewrite (applies nothing; reviewed as a diff) |
| `claim-accept-revision` | `--claim-id` — apply the pending rewrite to the claim text (human action; audited before/after) |
| `claim-reject-revision` | `--claim-id` — discard the pending rewrite; the claim text is unchanged |
| `claim-link-candidates` | `--claim-id`, `--intake-batch-id`, `--record-id` (repeatable; limit to specific hits) |
| `candidate-list` | `--claim-id`, `--show-text` |
| `claim-support-start` | `--claim-id`, `--candidate-id` |
| `claim-support-commit-human` | `--rating-id`, `--value <support>`, `--population-fit`/`--intervention-fit`/`--outcome-fit`/`--claim-fit` (0\|1\|2), `--rationale`, `--committed-by` |
| `claim-support-run-ai` | `--rating-id`, `--task-type` (blind, advisory; needs a pinned model + a rater) |
| `claim-support-compare` | `--rating-id` (concordance locks in the human value) |
| `claim-support-adjudicate` | `--rating-id`, `--final-value <support>`, `--rationale`, `--decider human\|panel` |
| `claim-support-show` | `--rating-id` |
| `claim-decide` | `--claim-id`, `--candidate-id`, `--decision accept\|reject\|needs_second_review\|accepted_with_caution`, `--reason`, `--rating-id`, `--decided-by` |
| `decision-list` | `--claim-id` |
| `claim-report` | `--format text\|md\|json`, `--output <file>`, `--show-text` — 4-state results; `--format md` is the editor-mode Citation-Integrity Report (read-only; CI-style exit) |
| `claim-commit` | `--decision-id`, `--collection-key`, `--commit` (default dry-run) — decision-gated Zotero write |
| `txn-list` | (read-only) list write transactions |
| `txn-show` | `--transaction-id` |
| `txn-undo` | `--transaction-id` — undo a committed write (deletes only what it created) |
| `warehouse-status` | (read-only) opt-in validation-warehouse status |
| `warehouse-emit` | `--claim-id`, `--candidate-id` — emit one de-identified record (no-op if disabled) |
| `warehouse-export` | `--output` |
| `warehouse-purge` | erase the warehouse (consent withdrawal) |

The **validation warehouse** (`config.validation_warehouse`) is opt-in and
**default-off**. When enabled it appends a *de-identified* record per final
decision — `claim_type`, a one-way claim-text hash, the public PMID/DOI, the
AI/human/final ratings, PICO fit, and agreement — with **no** identity,
manuscript text, Zotero keys, or project ids. Claim text is a top-sensitivity
tier stored only on a second opt-in (`include_claim_text`). Records are
append-only and purgeable.

`claim-commit` is the **decision-gated write**: it only writes for a final
`accept`/`accepted_with_caution` decision, refuses a candidate with no PMID/DOI
(anti-fabrication), previews by default, and on `--commit` records a
`ZoteroTransaction` carrying the full chain (claim · candidate · decision ·
provenance · audit · undo path). `txn-undo` reverses a committed write by deleting
**only the keys it created**, version-guarded so a user edit since creation aborts
the delete rather than clobbering it.

The **final decision** (`claim-decide`) is the human-owned terminal judgment per
(claim, candidate). The mission invariant is enforced: you cannot `accept` (or
`accepted_with_caution`) a candidate whose final support status does not support
the claim, and you cannot finalize accept/reject on an *unresolved* discordance
(adjudicate first, or record `needs_second_review`).

The claim-support rating answers *does this paper support **this claim**, and how
well does it fit?* — distinct from study quality (GRADE/RoB2). It rides on the
same dual-rating invariants: the human value is locked, the AI rating is blind +
advisory and never final, a discordance needs human/panel adjudication, and the
final value is never sourced from the AI. Support vocabulary: `directly_supports`,
`partially_supports`, `indirectly_supports`, `does_not_support`, `contradicts`,
`unclear`.

A claim records *what is asserted, where, and who/what extracted it*. Linking
*candidates* connects the claim to the papers that entered consideration for it
(from a staged intake batch), preserving the retrieval query/source/rank — but
asserting no support and writing nothing to Zotero. Candidates dedupe per claim
by normalized PMID/DOI. Everything is provenance-stamped and audited.

## Read / discover & evidence (read-only)

| Command | Key options |
|---|---|
| `extract` | `--citekey` \| `--item-key`, `--field` (repeatable), `--require-passage`, `--library`, `--show-quotes` |
| `claim-check` | `--claim`, `--citekey` (repeatable), `--require-page`, `--library`, `--show-quotes` |

## PubMed intake & surveillance

| Command | Key options |
|---|---|
| `literature-search` | `--query`, `--max-results`, `--include-abstracts`, `--library` |
| `import-results` | `--path`, `--format ris\|csv\|bibtex`, `--source-label`, `--library` |
| `surveillance-refresh` | `--query-id`, `--max-results`, `--library` |

## Corpus state

| Command | Key options |
|---|---|
| `snapshot` | `--label`, `--include-fulltext-hashes`, `--library` |
| `corpus-diff` | `--from`, `--to` \| `--current`, `--mark-stale`, `--library` |
| `map-bootstrap` | `--guideline-path`, `--write` (default dry-run), `--library` |

## Dual-rating, assessment, retraction, PRISMA

| Command | Key options |
|---|---|
| `rating-start` | `--frame-id`, `--scheme-id`, `--outcome-id`/`--study-id`/`--domain-id` |
| `rating-commit-human` | `--rating-id`, `--value`, `--rationale`, `--committed-by` |
| `rating-run-ai` | `--rating-id`, `--task-type` (refused without a model pin) |
| `rating-compare` | `--rating-id` |
| `rating-adjudicate` | `--rating-id`, `--final-value`, `--rationale`, `--decider human\|panel` |
| `assess` | `--frame-id`, `--scheme-id`, subject ids, `--value`, `--rationale`, `--dual-rating`, `--tag-mirror` |
| `retraction-scan` | `--citekey`/`--doi`/`--pmid` (repeatable), `--mark-stale` |
| `prisma-ledger` | `--question-id`, `--action init\|record_decision\|update_counts\|export`, `--payload <json>` |

## Reporting (read-only)

| Command | Key options |
|---|---|
| `evidence-export` | `--format csv\|markdown\|csl-json` (repeatable), `--citekey`/`--node-id`/`--outcome-id`/`--recommendation-id`, `--include-provenance`, `--include-ai-values` |
| `agreement-report` | `--metric raw_agreement\|cohen_kappa\|weighted_kappa\|adjudication_rate` (repeatable), `--format json\|csv\|markdown`, `--scheme-id`, `--task-type`, `--group-by` |

## Guarded write-back (dry-run first, token-confirmed)

All default to dry-run and print a one-use **confirmation token**; a real write
requires `--confirm-token <token>` for the *same* pending payload.

| Command | Key options |
|---|---|
| `note-add` | target, `--title`, `--markdown`, `--dry-run`/`--confirm-token`, `--show-body` |
| `tag-add` | targets, `--tag` (repeatable), `--confirm-token` |
| `tag-remove` | targets, `--tag` (repeatable), `--confirm-token` |
| `collection-add-item` | `--collection-key`, item targets, `--confirm-token` |
| `intake-push` | `--intake-batch-id`, `--record-id`, `--collection-key`, `--confirm-token` |
| `assessment-tag-mirror` | `--rating-id` \| `--assessment-attachment-id`, `--confirm-token` |

The live write backend is **unavailable/degraded by default**: a dry-run still
returns a diff preview + token, but a confirmed write fails cleanly with
`write_layer_unavailable` and a remediation string — and never falls back to the
Web API. Fake backends are used in tests.

> See `tests/` for executable examples of every command path, all offline.
