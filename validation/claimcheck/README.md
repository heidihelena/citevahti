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

# 2. two raters fill rater1 / rater2 (BLINDED — claim + passage only), then adjudicate.
#    Use the fill tool instead of hand-editing JSONL: it keeps blinding intact and
#    saves after every answer (resumable, crash-safe).
python validation/claimcheck/fill_ledger.py rater1
python validation/claimcheck/fill_ledger.py rater2
python validation/claimcheck/fill_ledger.py adjudicate   # reveals both raters
python validation/claimcheck/fill_ledger.py status       # progress / disagreements

# 3. score it
python validation/claimcheck/score_ledger.py validation/claimcheck/ledger.jsonl
#    (shortcut: python validation/claimcheck/fill_ledger.py score)
```

## Files

- `build_ledger.py` — seeds `ledger.jsonl` from the curated set; imports the
  repo's `text.py` so the seed reflects the real, shipped decision logic. Human
  columns left blank.
- `fill_ledger.py` — interactive, **blinded** filler for the human columns
  (`rater1` / `rater2` / `adjudicated`). Shows only the claim + passage while
  rating (never claim-check's status, the LLM, or the other rater), validates the
  relation vocabulary, verifies each pair's hash, and saves after every answer.
  Also `status` (progress + disagreements) and `score` (→ `score_ledger.py`).
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
