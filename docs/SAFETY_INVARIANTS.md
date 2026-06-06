# Safety invariants

These are hard invariants enforced in code and asserted by the test suite. Each
lists where it lives and the tests that guard it. They are the load-bearing
guarantees of the system; a reviewer should treat any violation as a defect.

| # | Invariant | Enforced in | Guarding tests |
|---|---|---|---|
| 1 | **No invented citekeys.** Citekeys resolve by exact match through Better BibTeX or are reported as orphans; never fabricated. | `cite.py`, `bbt/client.py`, `bibsync/`, `bootstrap/` | `test_cite.py`, `test_bibsync.py`, `test_map_bootstrap.py` |
| 2 | **No unsupported claim asserted as true.** `claim_check` returns only `supported_candidate` / `no_support_found` / `unverifiable`; never plain "supported", never asserts truth. | `claimcheck/service.py` | `test_claim_check.py` |
| 3 | **No field guessing.** `extract` is assistive; absent fields are `unverifiable` with `value: null`; values appear verbatim from source. | `extract/` | `test_extract.py` |
| 4 | **No AI final value.** `ai_rating.value` can never become `final_value` automatically; final is always human/panel-sourced. | `validators/rating.py`, `rating/engine.py` | `test_rating_validators.py`, `test_dual_rating.py` |
| 5 | **No discordant acceptance without adjudication.** A `discordant` record reaches a final value only via an `adjudicated` event with a rationale; `accepted` is concordant-only. | `validators/rating.py`, `rating/engine.py` | `test_rating_validators.py`, `test_dual_rating.py` |
| 6 | **No inclusion decisions by AI.** Intake records are pre-decision (`decision: null`); PRISMA rejects AI as decider; AI screening votes are `rating_id` references only. | `validators/intake.py`, `validators/prisma.py`, `prisma/service.py` | `test_prisma_ledger.py`, `test_surveillance_refresh.py`, `test_intake_push.py` |
| 7 | **No search-strategy design.** `literature_search` runs the verbatim user query; `surveillance_refresh` only mechanically appends a date constraint, never rewrites the query. | `intake/service.py` | `test_surveillance_refresh.py` |
| 8 | **No Zotero write without dry-run token confirmation.** Writes default to dry-run; apply requires a one-use, payload-bound, expiring token. | `writeback/layer.py` | `test_writeback.py`, `test_tag_mirror.py`, `test_intake_push.py` |
| 9 | **No silent local→Web-API fallback.** The write layer uses a single configured backend and never switches; unavailable → clean `write_layer_unavailable`. | `writeback/layer.py`, `writeback/backend.py` | `test_writeback.py::test_unavailable_backend_fails_cleanly_no_fallback` |
| 10 | **No title-only retraction truth.** Retraction is determined by DOI/PMID through a provider seam; items without DOI/PMID are skipped (warned), never matched by title. | `retraction/` | `test_retraction_scan.py` |
| 11 | **No title-only dedupe truth.** Library/intake dedupe uses normalized DOI (case-insensitive) and exact PMID; title alone never marks a duplicate. | `intake/dedupe.py`, `intake/service.py` | `test_bibsync.py`, `test_surveillance_refresh.py` |
| 12 | **No mutation during reporting exports** except the export audit event. `evidence_export` / `agreement_report` read only and write outputs under `exports/`. | `export/` | `test_evidence_export.py`, `test_agreement_report.py` |

## Supporting invariants

- **Human value is never overwritten** once committed and locked
  (`validators/rating.py::assert_human_value_unchanged`,
  `state/store.py::save_rating`).
- **AI provenance is always present and the model is pinned** for any AI rating
  (`validators/rating.py`); `rating_run_ai` refuses without an explicit model pin
  and refuses assist-only tasks such as `claim_check`.
- **`ai_abstained` / `human_only` never count as human–AI agreement**
  (`validators/rating.py::is_agreement_countable`, `export/agreement.py`).
- **Probe-not-proof, version separation**: capabilities are reported only after a
  successful probe; Zotero app version, schema version, and BBT version are kept
  distinct and never confused; the BBT version is read live, never hardcoded
  (`probe/probe.py`, `validators/probe.py`).
- **Tamper-evident audit**: every state mutation appends to a hash-chained log;
  `verify-audit` detects any retroactive edit (`state/audit.py`).
- **Tag-mirror discipline**: mirrors only human/final values, refuses AI-only and
  unadjudicated discordant values, and replaces the prior same-scheme tag rather
  than accumulating (`writeback/service.py`).
- **Offline tests**: the suite uses fake seams for HTTP, Zotero, BBT, PubMed, the
  AI rater, the retraction provider, and the write backend; no live network call
  or model invocation occurs.
