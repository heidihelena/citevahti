# Architecture

CiteVahti is a single-user, local tool. Its durable value lives in `.citevahti/`,
independent of any external service. Three external surfaces are consulted but
none is required for the stateful features to work.

## Four parts

1. **Zotero local API** — `http://localhost:23119/api/`, treated as
   **read-only / GET-only**. Source of truth for items, attachments,
   collections, indexed full text, and annotations. CiteVahti never writes here.
2. **Better BibTeX** — `…/better-bibtex/json-rpc` and `…/better-bibtex/cayw`.
   The citation engine: stable citekeys, exact-match resolution, export.
3. **Literature search providers** — PubMed via NCBI E-utilities (primary), plus
   OpenAlex, Semantic Scholar, and Crossref (DOI backfill), behind a pluggable
   interface. Search-only; stages results with provenance.
4. **`.citevahti/` state layer** — the durable provenance store.

`localhost` is used uniformly (the `/api/` path checks `Host: localhost:23119`).

## `.citevahti/` layout

```
.citevahti/
  config.json                 # endpoints, default library, rating config, AI provenance pin, writeback
  audit_log.jsonl             # append-only, hash-chained; every state mutation
  frames/<frame_id>.json      # version-stamped subjects + schemes + controlled vocab
  evidence_map.json           # typed nodes / links / attachments + citekey-centered reverse_index
  ratings/<rating_id>.json    # one subject × one scheme; distinct human/ai/comparison/adjudication
  claims/<claim_id>.json      # first-class manuscript claims (ADR-0001 spine)
  candidates/<claim_id>.json  # papers linked to a claim + retrieval provenance (ADR-0001 step 2)
  claim_support/<rating_id>.json # blinded human/AI claim-support ratings + PICO fit (ADR-0001 step 3)
  decisions/<decision_id>.json # human-owned final decision per (claim, candidate) (ADR-0001 step 4)
  transactions/<txn_id>.json  # decision-gated Zotero write transactions + undo snapshot (ADR-0001 step 5)
  validation/records.jsonl    # opt-in, de-identified validation warehouse (append-only) (ADR-0001 step 6)
  intake/<batch_id>.json      # staged PubMed/manual candidate records (decision: null)
  snapshots/<snapshot_id>.json
  prisma/<question_id>.json   # human-only PRISMA decisions + derived counts
  exports/{evidence,agreement}/<run_id>/   # neutral reporting artifacts
  pending/<token>.json        # write-back confirmation-token bookkeeping (one-use)
```

## Package map (`src/citevahti/`)

| Module | Responsibility |
|---|---|
| `probe/` | Probe-not-proof startup checks; version parsing; capability gating |
| `state/` | `CiteVahtiStore` (atomic writes), hash-chained `AuditLog` |
| `schemas/` | Pydantic schemas: common, config, frame, rating, evidence_map, intake, snapshot, corpus, bootstrap, results, prisma, export, writeback |
| `validators/` | Binding invariants: config (model pin / task split), frame/subject keying, rating validity, evidence map, intake, prisma, probe |
| `zotero/` | Read-only Zotero local-API access (library selector) |
| `bbt/` | Better BibTeX JSON-RPC client (citekey resolution) |
| `cite.py` | `cite` (never invents keys) |
| `bibsync/` | Multi-file citekey extraction, resolution, export |
| `evidence/` | Evidence-map operations + reverse-index upkeep |
| `retrieval/` | Deterministic passage retrieval over full text + annotations |
| `extract/`, `claimcheck/` | Assistive extraction; lexical claim support |
| `claims/` | Claims (ADR-0001 spine), claim↔candidate linkage, and the blinded claim-support dual-rating engine |
| `agent/` | Constrained agent (MCP) surface — only safe verbs, policy-enforced (`docs/AGENT.md`) |
| `report/` | Read-only 4-state citation-integrity report (the VS Code / editor-mode data) |
| `capabilities.py` | Connection & Capabilities report (`citevahti status`) |
| `pubmed/`, `intake/` | PubMed provider; intake staging + dedupe + surveillance |
| `corpus/`, `bootstrap/` | Snapshots, corpus diff, minimal map bootstrap |
| `rating/`, `assess/` | Dual-rating engine + `AiRater` seam; human-chosen assessment |
| `retraction/`, `prisma/` | Retraction scan (provider seam); PRISMA ledger |
| `export/` | `evidence_export`, `agreement_report`, kappa stats |
| `writeback/` | Guarded write layer, backends, write service |
| `tools.py` | Public tool façade |
| `cli.py` | `citevahti` CLI |

## Seams (why tests run offline)

Every external dependency is reached through an injectable seam with a
deterministic fake double:

- **HTTP**: `HttpClient` (probe/Zotero/BBT) — `FakeHttpClient` in tests.
- **Citekey/text**: `TextSource` — `StaticTextSource`.
- **PubMed**: `LiteratureProvider` — `FakeProvider`.
- **Library dedupe**: `LibraryDedupeIndex` — `StaticLibraryIndex`.
- **Corpus**: `CorpusSource` — `StaticCorpusSource`.
- **AI rating**: `AiRater` — `FakeAiRater` (no model is ever called in tests).
- **Retraction**: `RetractionProvider` — `FakeRetractionProvider`.
- **Write-back**: `WriteBackend` — `FakeWriteBackend` / `UnavailableBackend`.

The live default for the AI rater, retraction provider, and write backend is
**unavailable/degraded** unless explicitly configured; nothing makes network
writes or hosted-model calls by default.

## Audit log

`audit_log.jsonl` is append-only and hash-chained: each entry hashes the
previous entry's hash, so a *partial* retroactive edit or deletion breaks the chain
and is caught by `verify-audit`. The chain is **tamper-evident, not cryptographically
signed** — it surfaces accidental corruption and naive edits, but a deliberate re-hash
of the whole log would still validate. A signed / research-grade audit trail is out of
beta scope (and not required by e.g. PRISMA); the threat model is honest-researcher
provenance, not defending against the researcher. Reporting exports and write-back use distinct
event types (`export.evidence`, `export.agreement`, `zotero.write.applied`) so
that export creation is never confused with evidence mutation.
