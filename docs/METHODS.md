# Methods

This document describes the human → AI → adjudication dual-rating workflow as it
is actually implemented, so it can be reported transparently in a methods
section. It reports **what the system does**; it does **not** claim compliance
with, or endorsement by, any reporting guideline.

The **AI second rating is an optional, blinded second opinion — not mandatory.**
The human always decides (Invariant 1). A decision resolves and may be written when
it is *concordant*, *adjudicated*, *ai_abstained*, *ai_failed*, **or** *human_only* (a human rating
with no AI rating). "human → AI → adjudication" names the full dual-rating path; the
AI leg can be skipped, and a human-only accept is by design, not a gap.

## Dual-rating workflow

For each judgment (one subject × one scheme):

1. **`rating_start`** — open a record bound to `frame_id` + `frame_version` +
   `scheme_id` + a subject key validated against the scheme's unit:
   - GRADE certainty: `outcome_id` (outcome / body-of-evidence level).
   - RoB 2 / ROBINS-I: `study_id`, or `study_id × outcome_id` if configured.
2. **`rating_commit_human`** — the human commits a controlled value **blind**.
   The human value **locks on commit and is never overwritten**.
3. **`rating_run_ai`** — the AI rates **blind to the human value** (see Blinding).
   It may abstain. It records full provenance and never writes `final_value`.
4. **`rating_compare`** — sets the comparison status (see below).
5. **`rating_adjudicate`** — a human or panel resolves a discordance with a
   rationale. The recorded `final_value` is always human/panel-sourced.

Every step appends an audit event.

## Blinding model

- Default order is `human_first_ai_blind` (configurable).
- The `AiRater` seam's signature **excludes any human value**; the AI never
  receives it. The blinding `access_log` records seal/commit events, and each
  record carries an `independent` flag.
- Human↔human independence (multi-rater) is supported by per-rater records and a
  sealed commit-then-reveal discipline recorded in the access log.

## AI abstention handling — and why a failed call is not an abstention

- The AI may return `abstained = true` with no value. An **abstention is a rating
  outcome**: the model read the item and declined to rate it.
- A call that produced no judgement at all is recorded as a **failure**, never as an
  abstention. `ai_rating.failure` carries the kind, and the two fields are mutually
  exclusive:

  | `ai_rating.failure` | what happened |
  |---|---|
  | `provider_error` | the endpoint returned no readable reply — the model never spoke |
  | `truncated_reply` | the reply hit the token ceiling before an answer |
  | `unparseable_reply` | the model replied, with no readable JSON verdict |
  | `out_of_vocab_value` | it answered outside the controlled vocabulary |

  The distinction is load-bearing for reporting: "the AI abstained" tells a reader the
  model exercised judgement, so an adapter or transport fault reported in those words
  overstates what the model did while hiding a defect in the pipeline. Neither value is
  ever fabricated in either case.
- A `truncated_reply` also records **the reply-token budget that was in force**, and what
  the provider says the reply spent, so the setting to change is named in the record. Read
  those two numbers for what they are: a reply cut off at the ceiling spent *exactly* the
  ceiling, so they are never a measured shortfall. How much the item would have needed is
  not knowable from a cut-off reply — and sometimes there is no such number. Measured
  2026-07-27, qwen3:14b over the 44-pair prescreen corpus with the ceiling set
  deliberately non-binding: median 269 completion tokens, the largest **answered** reply
  2396 — and one item that spent 8192 tokens over 489 s and returned nothing, exactly as
  it had spent all 2048 at the shipped ceiling. The local default therefore clears the
  tail that ends (4096) and does not pretend to clear the tail that does not.
- Both are recorded with full provenance, and both are **excluded from the human–AI
  agreement denominator** — but they are **counted and described apart from each other**
  in the agreement report and the auto-filled methods statement.
- Records written before `ai_rating.failure` existed carry `None` there and are **not**
  reclassified retroactively; the distinction begins where it was recorded.

## Comparison statuses

| `comparison.status` | meaning | agreement outcome |
|---|---|---|
| `concordant` | human value == AI value | `accepted` (human value locked in) |
| `discordant` | human value != AI value | `needs_adjudication` |
| `ai_abstained` | AI ran, read the item, and declined to rate | excluded from agreement |
| `ai_failed` | the AI call returned no rating — not a judgement | excluded from agreement |
| `human_only` | no AI rating present | excluded from agreement |

`concordant` auto-accepts the **human** value via an `accepted` event — the AI
value is never the source even when it happens to match.

## Adjudication rule

- A `discordant` record can reach a `final_value` **only** through an
  `adjudicated` event with a `decider` of `human` or `panel` and a rationale.
- `accepted` applies only to a concordance and pins `final_value` to the locked
  human value.
- The AI value is **never** copied to `final_value` automatically.

## AI provenance fields

Every AI rating carries:

- `provider`, `model_id`, `model_snapshot` (dated/version snapshot),
- `prompt_template_version`, `prompt_hash`, `config_hash`,
- `rated_at`, and the blinding record (`mode`, `access_log`, `independent`).

The model must be **explicitly pinned** (the config default is a `PENDING`
sentinel); `rating_run_ai` refuses to run otherwise. AI rating tasks
(`extract`, `assess`; optional, off-by-default `screen_vote`) are distinct from
assist tasks (`claim_check`), which `rating_run_ai` refuses.

## Agreement & adjudication reporting

`agreement_report` reads rating records only and changes nothing.

**Both rated instruments are covered**: study-quality ratings (GRADE / RoB, keyed to
subject × scheme) *and* claim-support ratings (keyed to a claim–candidate pair). The
latter carry no frame or scheme record, so they are reported under the reserved scheme id
**`claim_support`**. They are counted, but **never pooled** with a study-quality scheme
into a single agreement figure — two instruments on two units are not one number. Group
by `scheme_id` to get an honest κ for each.

- **raw agreement**, **Cohen κ** (nominal; guarded for insufficient variation),
  **ordinal weighted κ** (quadratic; ROBINS-I *No information* is missing-like
  and is excluded + reported), **adjudication rate** with pending counts.
- Refuses κ across mixed schemes unless grouped by scheme; warns on mixed frame
  versions.
- **Refuses ordinal weighted κ for `claim_support`** (`error: no_ordinal_scale`). The
  support vocabulary has no defined ordinal ranking — `overstated` and `unclear` are not
  points on a strength continuum — so weighting it would require inventing a scale the
  instrument does not have. Cohen's κ (nominal) is the reported statistic there.
- Adjudicated records are counted by their **original** human–AI comparison, not
  the final adjudicated value.
- An AI-provenance summary (model ids, snapshots, prompt-template versions,
  prompt/config hash counts, dates, blinding modes, abstention counts, task
  types) is included.

### Which numbers the methods statement reports

Every sentence of the auto-filled methods paragraph is about claim–candidate support on
the support vocabulary, so its counts, raw agreement and κ are **scoped to the
claim-support ratings**. A ledger that also holds study-quality ratings is told so in a
*Before you submit* note, with a pointer to `agreement_report` for those — they are
neither pooled into the paragraph nor silently dropped from the packet.

## PRISMA-trAIce / RAISE-style transparency

`agreement_report` emits a Markdown **method-transparency section** that states:
the AI role, task types where AI was used, blinding mode, abstention handling,
comparison rule, adjudication rule, human/panel final authority, the model
provenance summary, the agreement metrics, and limitations.

This section **reports what was done**. It does **not** assert compliance with,
or endorsement by, PRISMA 2020, PRISMA-trAIce, RAISE, or any other framework, and
its metrics are descriptive — they do not validate the AI, establish ground
truth, or substitute for human judgment.
