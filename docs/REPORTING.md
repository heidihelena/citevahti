# Reporting CiteVahti in your methods section

CiteVahti's value is a documented **human → AI → adjudication** workflow you can
report transparently. This page turns that promise into paste-able text: which
commands produce the numbers, a fill-in-the-blanks methods paragraph, and what
each placeholder means. Nothing here claims compliance with any reporting
guideline — it reports *what was done*.

## The two artifacts

| Artifact | Command | What it is for |
|---|---|---|
| **Citation-Integrity Report** | `citevahti claim-report --format md` | The per-claim test results a supervisor, co-author, or editor reads. Carries its own scope-and-limitations footer, audit-chain head, completeness denominator, and retraction status. |
| **Agreement report** | `citevahti agreement-report --metric raw_agreement --metric cohen_kappa --metric adjudication_rate --format markdown` | Human–AI agreement metrics plus the **method-transparency section** — the ingredients for your methods paragraph. Written to `.citevahti/exports/agreement/<run-id>/agreement.md`. |

Both are read-only: they compute no new judgments and change nothing.

## Fill-in-the-blanks methods paragraph

Copy, fill, and adapt. Every placeholder maps to a line in the agreement
report's *AI-in-evidence-synthesis method transparency* section (or to your
ledger's config).

> Citation–evidence support was assessed claim by claim using CiteVahti
> v__VERSION__ (Vahtian; Apache-2.0), which records a blinded dual-rating
> workflow: for each claim–candidate pair, a human rater first recorded a
> support rating (scale: directly_supports / partially_supports /
> does_not_support / contradicts / unclear) while the AI second opinion was
> withheld; an AI rater (__PROVIDER__, model __MODEL_ID__, snapshot
> __SNAPSHOT__, prompt template __PROMPT_VERSION__) independently rated the
> same pair without access to the human value. Rating order
> (__BLINDING_MODE__, e.g. human_first_ai_blind) and timestamps were recorded
> in a hash-chained audit log. Of __N_PAIRS__ comparable human–AI pairs,
> __N_AGREE__ were concordant and __N_DISAGREE__ discordant
> (raw agreement __RAW_AGREEMENT__; Cohen's κ __KAPPA__). AI abstentions
> (__N_ABSTAIN__) were excluded from the agreement denominator. Every
> discordance was resolved by human adjudication with a recorded rationale;
> AI values were advisory only and never set the recorded final value.
> CiteVahti checks citation support, not the truth of the underlying claims.

Where each number comes from:

- `__VERSION__` — `citevahti --version` (or `pip show citevahti`).
- `__PROVIDER__ / __MODEL_ID__ / __SNAPSHOT__ / __PROMPT_VERSION__` — the
  **Model provenance** line of the transparency section (pinned in
  `.citevahti/config.json` → `ai_provenance`).
- `__BLINDING_MODE__` — the **Blinding mode** line (config `rating.order`,
  plus the modes actually observed in the ledger).
- `__N_PAIRS__ / __N_AGREE__ / __N_DISAGREE__ / __N_ABSTAIN__` — the
  **Agreement metrics** and **Abstention handling** lines.
- `__RAW_AGREEMENT__ / __KAPPA__` — the per-group `metrics` block
  (group by `scheme_id` if you rated under more than one scheme; κ is refused
  across mixed schemes rather than computed wrongly).

## Describing the blinding honestly

If a reviewer asks what "blinded" means here, the precise sentence is:

> The AI rater is structurally blinded — the rating interface never passes the
> human value to it. The human-first order is enforced by the review surface
> (the AI's rating is withheld until the human rating is committed) and
> verified from the audit log's rating modes and timestamps, rather than being
> a cryptographic guarantee.

This matches how single-blind screening in standard systematic-review tooling
is reported, and it is exactly what the ledger can substantiate.

## Worked example (demo ledger)

Regenerate any time:

```bash
PYTHONPATH=src python3 docs/demo/build_demo_ledger.py .demo-ledger
citevahti --root .demo-ledger claim-report --format md > integrity.md
citevahti --root .demo-ledger agreement-report --metric raw_agreement --format markdown
```

The integrity report ends with the footer your reader needs (real output):

```markdown
**Scope & limitations** — read before relying on this report.

- **Coverage:** this report covers 5 of the 5 claim(s) recorded in the ledger.
  Claims enter the ledger only when the author adds them; the report cannot
  certify that every claim in the manuscript was entered.
- **Integrity:** audit chain of 40 entries, head `190805281d454345…`, intact at
  generation. The chain is tamper-evident, not cryptographically signed: it
  shows the recorded order of work, but a regenerated ledger would also
  validate. Treat it as honest-researcher provenance, not forgery-proof
  certification.
- **Retractions:** checked via OpenAlex is_retracted, matched by DOI/PMID only —
  items without a DOI or PMID are not checked; last scan: never. Absence of a
  flag is not proof a work is unretracted.
- **Meaning of verdicts:** states record citation support as rated in the
  blinded human → AI → adjudication workflow — not clinical or scientific truth.
```

The agreement report's transparency section renders even before any dual
ratings exist (counts read zero); the metrics populate as you rate.

## For supervisors and editors

The report audits the *author's own verification process* — it does not
independently re-verify their citations. What you can check:

1. The **coverage line**: how many ledger claims the report covers, and that
   the count is plausible for the manuscript's citation density.
2. The **audit head + entry count**: ask for `citevahti verify-audit` output
   (exit 0, same head hash) if you want to confirm the ledger behind the
   report is intact.
3. **Discordances**: every `review_needed` claim and every adjudication has a
   recorded rationale — spot-check those rather than the concordant majority.
4. The **retraction line**: a recent scan date, and no RETRACTED flags.

What the report cannot prove: that every claim in the manuscript was entered,
or that the ledger was not regenerated wholesale. It is honest-researcher
provenance, not a forgery-proof certificate (see the **Tamper-evident audit**
invariant in `SAFETY_INVARIANTS.md`).
