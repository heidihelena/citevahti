# claim-check measurement ledger

A pre-registered way to make claim-check **more accurate without guessing**. You
cannot improve what you do not measure, so measure *before* you tune the
threshold, the stopword list, or anything else.

The companion correctness fix (the polarity guard that stops a contradicting
source being returned as support) already shipped — see `CHANGELOG.md` and
`tests/test_claimcheck_polarity.py`. This folder is the **measurement** half.

## The unit of analysis

A **(claim, passage) pair** — exactly what claim-check decides — hand-curated,
**not** auto-mined from abstracts. Two blinded humans each label a
`relation ∈ {supports, contradicts, neither}`; their adjudicated consensus is the
ground truth. Two detectors are scored against it:

- **support detector** — predicts support iff `status == supported_candidate`
- **contradiction detector** — predicts contradiction iff `status == contradiction_candidate`

…on precision / recall / F1. **Cohen's κ is reported first**: if the raters don't
agree, there is no usable ground truth and the metrics are void until the rubric
is sharpened. An optional LLM advisor is scored against the **same human gold**
(never against claim-check), and the **correlated-error** count is shown so
agreement is not mistaken for accuracy.

## Workflow

```bash
# 1. seed the ledger from the curated set, using the repo's real (patched) text.py
python validation/claimcheck/build_ledger.py            # -> ledger.jsonl (human cols blank)

# 2. two raters fill rater1 / rater2 (blinded), then adjudicate -> adjudicated.relation
#    (edit ledger.jsonl by hand; it is append-only JSONL, one record per line)

# 3. score it
python validation/claimcheck/score_ledger.py validation/claimcheck/ledger.jsonl
```

## Files

- `build_ledger.py` — seeds `ledger.jsonl` from the curated set; imports the
  repo's `text.py` so the seed reflects the real, shipped decision logic. Human
  columns left blank.
- `score_ledger.py` — metrics from a filled ledger; **refuses to invent labels**
  (reports what is missing instead).
- `make_demo_ledger.py` + `ledger.demo.jsonl` — an **ILLUSTRATIVE** synthetic
  fill so you can see the output shape. **Cite no number from it.**
- `ledger.jsonl` — the seeded ledger (real claim-check decisions, blank human
  columns) awaiting adjudication.

## Discipline (mirrors MatchVahti's validation protocol)

1. The polarity guard is a **correctness fix** — already shipped; it's a bug, not
   an opinion.
2. **Measure before tuning** — fill the ledger with two raters, get κ ≥ 0.6, then
   precision / recall. Only then touch the threshold or lexicon.
3. **Semantic gains are an advisory layer** (LLM / NLI / embeddings), kept
   advisory and measured against the same human gold. Lexical claim-check stays
   the transparent, auditable floor.
