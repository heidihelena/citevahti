# ADR-0001 — ZotSynth is Citation Integrity Infrastructure

- **Status:** Accepted (2026-06-03 — all four open decisions ruled; see §8)
- **Date:** 2026-06-03
- **Supersedes:** the implicit "local citation/evidence tool" framing in
  `docs/ARCHITECTURE.md` (that document stays accurate for v0.x; this ADR sets
  the direction the schema and product evolve toward).

## 1. Context

A product manifesto + data-architecture brief reframes ZotSynth. The category
is **not** Paper → Library → Organization. It is:

```
Claim → Evidence → Validation → Decision → Audit → (Zotero write)
```

The thesis: reference management is solved; **evidence judgment is not**, and AI
makes claim generation nearly free while verification stays expensive. ZotSynth
exists to reverse that asymmetry. The lasting value is not the UI, the Zotero
integration, or the AI — it is the **evidence-decision ledger**: claim → candidate
→ AI rating → human rating → final decision → audit, repeated at scale.

This ADR records that decision and, crucially, reconciles it with what the code
**actually is today** so the gap is explicit and the migration is honest.

## 2. Decision

1. **Category:** ZotSynth is *Citation Integrity Infrastructure* / *Evidence
   Validation for AI-Assisted Research*. Not a citation manager, search tool, or
   chatbot. Every feature must answer **"does this help someone make a better
   evidence decision?"** — if not, it is rejected.
2. **The claim is the spine.** The first-class object is the **claim**, with
   candidate papers hanging off it — not the paper with claims as an afterthought.
   (Today the spine is the *citekey/paper*; see §4. This is the largest change.)
3. **The ledger is the product.** Store the *reasoning*, never only the outcome.
   The append-only, hash-chained audit log is the integrity backbone and is
   preserved and strengthened — not replaced by a decorative log.
4. **Writes are decision-gated.** A reference may enter Zotero only as the
   terminal step of a validated decision (see the invariant in §6).
5. **Two data layers, separated early in design but not prematurely in code:** an
   operational store for the app, and an append-only validation warehouse that
   becomes the reusable validation asset (see §5).

## 3. What this is NOT (explicit non-goals)

From the manifesto, and binding: no literature map, no AI-chat-over-PDFs, no
folder-color/organization features, no animated dashboards, no
confidence-score-only UI, no "AI approved" language. Trust comes from **visible
uncertainty** (show AI vs human disagreement), not from impressiveness.

> **Honest flag (self-review):** the in-progress `collection-audit` /
> "clean, tagged, annotated collection" work sits in the *organization* quadrant
> the manifesto rejects. Under this ADR it is **deprioritized** unless it is
> re-scoped to surface *decision* gaps (claims with no accepted evidence,
> unsupported accepted citations, retraction exposure) rather than tag/field
> tidiness. Recorded here so we don't quietly keep building the wrong quadrant.

## 4. Current state → target (the honest gap)

| Manifesto object | Today in `.zotsynth/` (v0.2) | Gap to close |
|---|---|---|
| `claims` (first-class, with `manuscript_location`, `claim_type`, extraction provenance) | **None.** `claim_check` takes a claim *string* transiently; `evidence_map` has a `verified_claim` *attachment*. | Promote **claim** to a first-class entity. This is the spine change. |
| `papers` (canonical, unique pmid/doi) | `CorpusItem`/snapshots + Zotero items; DOI/PMID dedupe exists (`intake/dedupe.py`). | Add a canonical papers table with unique pmid/doi; reuse the existing normalizers. |
| `claim_paper_candidates` (why a paper entered consideration) | `intake/<batch_id>.json` records `retrieval_query`, source, rank, dedupe_status — but tied to a **query batch**, not a **claim**. | Re-key candidates to a `claim_id`; keep retrieval provenance. |
| `evidence_ratings` (support + PICO fit) | `RatingRecord` (blinded human/ai/comparison/adjudication) — **strong match in structure**. | **But:** today's schemes rate study *quality* (GRADE/RoB2/ROBINS-I). The manifesto's core asset is *claim-support* (`directly_supports … contradicts`) + population/intervention/outcome/claim **fit**. These are a **different, additional rating dimension**. `claim_check` is its lexical seed, not the rated judgment. |
| `final_decisions` (accept/reject/second-review/with-caution) | `adjudicate` (per rating) + PRISMA (inclusion). | Add a per-(claim,paper) `final_support_status` + `final_decision`. |
| `audit_events` (append-only, before/after, provenance) | `audit_log.jsonl` — append-only **and hash-chained** (`verify-audit`). | **Already ahead of the brief:** keep the hash chain; the warehouse `audit_events` MUST inherit it (the manifesto omits integrity hashing — do not regress). |
| `zotero_transactions` (preview/commit/undo/failed + undo_snapshot) | `pending/<token>.json` (one-use token) + `zotero.write.applied`/`.failed`. | Promote to a **transaction object** with an `undo_snapshot` and an `undone` state. (This is also the stress-test's "no undo" gap.) |
| `validation_records` (de-identified, reusable) | **None.** | New warehouse; see §5 + the privacy flag in §7. |

**Takeaway:** the *rating/adjudication/audit machinery already exists and is
high quality.* What's missing is (a) the **claim** as the organizing entity,
(b) a **claim-support** rating dimension distinct from study-quality, and
(c) the **transaction + undo** wrapper around writes.

## 5. Data architecture (target)

```
PostgreSQL              = operational source of truth
pgvector                = semantic retrieval (NOT audit, NOT truth)
object storage (S3)     = raw documents / logs / exports
append-only event table = audit (hash-chained, carried over from v0.x)
Redis + queue worker    = PubMed / Zotero async tasks
```

- **Operational DB** (serves the app): `users, projects, manuscripts, claims,
  papers, claim_paper_candidates, evidence_ratings, final_decisions,
  zotero_transactions, audit_events`. That is the MVP schema — do not overbuild.
- **Validation warehouse** (the reusable validation asset): append-only claim-paper pairs, AI ratings,
  human ratings, disagreements, final decisions, fit scores, provenance. Built so
  labels **emerge from the workflow** (a reviewer clicking "Directly supports"
  *is* the label) — never a separate labeling chore.
- **Schema versioning is mandatory** on ratings/provenance; the rating model will
  evolve and old records must remain interpretable.

The current local file layout is, in effect, a **single-user prototype of the
operational DB**. Each `.zotsynth/` file maps cleanly to a table; the hash-chained
JSONL is the prototype of `audit_events`. This makes the local tool a faithful,
testable reference implementation of the hosted schema — a feature, not debt.

## 6. The key invariant (the product, stated as a rule)

> Every accepted Zotero reference MUST have: **one claim, one paper, one final
> support decision, one provenance record, one transaction, one audit trail, one
> undo path.** If any is missing, **the write does not happen.**

This is enforceable and testable. It is also a **behavior change**: today
`intake_push` can add a paper to Zotero from a search batch with **no claim and
no decision**. Under this invariant that path is no longer allowed (or must be
explicitly marked as a non-validated "staging" write, clearly outside the
integrity guarantee). See decision D2 in §8.

## 7. Privacy & data boundaries

Hard separation between **sensitive user content** (manuscript text, unpublished
claims, identity, Zotero library data) and **reusable validation data**
(normalized claim, claim_type, paper metadata, rating outcome, fit scores,
agreement status).

> **Honest flag (self-review):** "de-identified `normalized_claim_text`" is a
> **weak guarantee**. A normalized claim can still reveal an unpublished
> hypothesis and may be re-identifying in a small field. Recommendation:
> (a) the validation warehouse is **opt-in with explicit consent**, default off;
> (b) claim text used for training is stored only under that consent, and
> separable/eraseable per project; (c) at minimum, store the **claim_type +
> structured fit + ratings** (low re-identification risk) and treat raw
> normalized claim text as the highest-sensitivity tier. This preserves the reusable validation asset
> while not turning the product into a manuscript-harvesting system.

Secrets: the existing posture (OS keyring, env escape hatch, never in
config/logs/exports, `secret_state`/`secret_source` reveal *source not value*)
carries over unchanged.

## 8. Decisions (ruled 2026-06-03)

- **D1 — Claim-support rating dimension: ACCEPTED.** Add a new scheme
  (`directly_supports … contradicts` + population/intervention/outcome/claim fit
  0–2) **alongside** the study-quality schemes (GRADE/RoB2/ROBINS-I). It reuses
  the existing blinded dual-rating/adjudication machinery; `claim_check` is its
  lexical seed, not the rated judgment.
- **D2 — Decision-gated writes: ACCEPTED (strict + labelled staging).** Validated
  writes require the full §6 invariant. A non-validated "staging" write remains
  available **only** when explicitly flagged as outside the integrity guarantee
  (it must not claim a final decision, and the audit event records it as staging).
- **D3 — Build target: ACCEPTED (local file model first).** Evolve `.zotsynth/`
  into the claim + transaction + undo prototype. The offline test suite is the
  executable spec; the schema is de-risked before any hosted Postgres build.
- **D4 — Validation warehouse: ACCEPTED (opt-in, default-off).** Off unless the
  user consents; claim text is the top-sensitivity tier, separable/eraseable per
  project; structured fit + ratings (low re-id risk) are the default contents.

## 10. Implementation sequence (local-first, each step reviewed)

Derived from the rulings. Each step is its own branch with offline tests,
stopping for review — same discipline as the original nine-step build.

1. **Claim entity + store. ✅ done.** `schemas/claim.py` (`Claim`: id,
   project/manuscript, `claim_text`, `claim_type`, `manuscript_location`,
   extraction provenance); `.zotsynth/claims/<claim_id>.json`; audited CRUD.
2. **Claim ↔ candidate linkage. ✅ done.** Intake hits linked to a `claim_id`
   (`candidates/<claim_id>.json`), preserving retrieval query/source/rank/
   why-found; deduped per claim by normalized PMID/DOI.
3. **Claim-support rating scheme (D1). ✅ done.** Controlled support vocabulary +
   PICO fit subscores, on a `(claim, candidate)`-keyed `ClaimSupportEngine` that
   reuses the proven value blocks + invariants (blinded human/AI, comparison,
   adjudication). (`agreement_report` over the support dimension is a follow-up.)
4. **`final_decisions` per (claim,paper). ✅ done.** `accept | reject |
   needs_second_review | accepted_with_caution`, with the final support status +
   agreement status; the human-owned terminal step. Mission invariant enforced:
   no `accept` on a non-supporting status; no finalizing an unresolved discordance.
5. **Zotero write transactions + undo (D2). ✅ done (validated path).** A
   `ZoteroTransaction` (`previewed | committed | undone | failed`) with an
   `undo_snapshot`; `commit_for_decision` enforces the §6 invariant (write only
   for an `accept` decision, full chain, anti-fabrication); `undo` deletes only
   the keys it created, version-guarded. `intake_push` remains the
   explicitly-labelled non-validated **staging** path (follow-up: route it through
   a transaction too).
6. **De-identified `validation_records` (D4). ✅ done.** Opt-in, default-off,
   append-only `validation/records.jsonl`; written only when enabled; claim text
   gated behind a second opt-in (`include_claim_text`); no identity / manuscript
   text / Zotero keys / project ids; purgeable (consent withdrawal). Labels emerge
   from the workflow via `auto_emit` on a final decision.

Steps 1–4 have **no new external dependency** and keep the tool fully offline +
testable. Step 5 builds on the existing write layer. Step 6 is gated behind
consent and can trail.

## 9. Consequences

- **Positive:** a single coherent thesis aligns schema, product, and business;
  the existing dual-rating + hash-chained audit becomes the asset engine; the
  reviewer's undo and "create/select collection" gaps fall out of the
  transaction + decision-gated design naturally.
- **Negative / cost:** the claim-spine reorientation touches the data model;
  decision-gated writes change `intake_push` behavior; the warehouse adds consent
  and governance obligations.
- **Carried forward unchanged:** probe-not-proof, read-only Zotero local API,
  exact-query preservation, no-silent-fallback, secrets posture, and the
  hash-chained audit log.
