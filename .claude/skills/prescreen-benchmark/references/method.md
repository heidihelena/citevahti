# Method, findings, and gotchas

## What the run measures
Each pair is a `claim ↔ cited-source-snippet`. Every rater assigns one of four labels
(`supports`/`contrasts`/`unclear`/`not_relevant`). The **anchor** (`ref_status`) is the
reference; each model's agreement with the anchor (raw % and Cohen's κ) is the score, plus
pairwise agreement between raters. `bench.py` also emits a `ValidationRecord`-shaped JSONL
corpus (one row per pair × rater) that conforms to CiteVahti's de-identified warehouse schema.

## The confound to state every time (agreement ≠ accuracy)
In the runs this skill was built from, Claude authored the claims, snippets, **and** the anchor
**and** the "Claude" ratings. That makes "Claude 100%" largely *self-consistency*, not
independent accuracy, and gives Claude a shared-language edge the local models don't have. The
fix is an anchor authored independently of every rater (domain expert or cited guideline), with
all models — Claude included — scored through the identical blind prompt. Until that's done, the
Claude column is a strong-model *reference peer*, not ground truth, and the write-up must say so.

## Findings so far (three 40-pair themes; anchor authored by Claude — see confound)
| Theme | qwen3:14b | hermes3:8b | Claude (ref) |
|---|---|---|---|
| lung-nodule-management | 88% / κ0.80 | 80% / κ0.68 | 100% / κ1.0 |
| lung-cancer-risk-factors | 95% / κ0.93 | 82% / κ0.75 | 100% / κ1.0 |
| lung-cancer-neoadjuvant | 85% / κ0.79 | 90% / κ0.86 | 100% / κ1.0 |

- **The "unclear" category is the consistent weak spot.** Across all 120 pairs, every case where
  *both* local models diverged from the anchor was an `unclear` case. The models under-produce
  the `unclear` verdict and leak that uncertainty in opposite directions: **qwen → contrasts**
  (reads "not established" as "contradicted"); **hermes → supports** (credulous, waves through
  overstated/false claims).
- **No stable local winner** — qwen won two themes, hermes one. Which small model looks better
  depends on the topic's uncertainty texture.
- **The gap is largely a prompt/workflow problem for a mid-size model.** A v2 prompt that
  explicitly scaffolds `unclear` ("'not established/inconclusive/uncertain' ⇒ unclear, NOT
  contrasts") took **qwen3:14b 85% → 98%** on neoadjuvant (unclear recall 2/8 → 7/8). The same
  prompt took **hermes3:8b 90% → 88%**: it fixed unclear (5/8 → 8/8) but broke genuine
  contradictions — an 8B **capacity ceiling** (fixing one branch degrades another). Use
  `prompt_v2.py` to reproduce this diagnostic per theme.
- **Inter-model agreement is not a correctness signal.** In the 2 (of 8) cases where the two
  local models agreed with each other against the anchor, they were both wrong. Practical rule:
  treat any `unclear`-region claim as human-review-required regardless of model consensus.

## Gotchas
- **qwen3 (and any thinking model) needs `think:false`.** With Ollama's native `/api/chat`, pass
  `"think": false` (bench.py does this via `THINKING_MODELS`). Without it qwen3 either runs very
  slow or returns empty `{}` under `format:json`. NOTE: CiteVahti's `HttpAiRater` calls the
  OpenAI-compat `/v1` endpoint, which has **no** `think:false` — so a qwen3-family model
  misbehaves through the product adapter as written. That's the one code fix this study surfaced
  (pair it with the prescreen prompt scaffolding above).
- **Latency is cold-load dominated.** First call per model can be 20–40s; warm calls are ~1.5–3s.
  Don't report the cold number as steady-state.
- **Class balance.** Aim for real `unclear` and `not_relevant` cases. A seed that is all
  supports/contrasts hides the exact weakness worth measuring, and inflates κ.
- **Store ingest rules (`ingest.py`).** The final decision must be consistent with the support
  value: `accept` only for supporting values (`directly/partially/indirectly_supports`),
  `reject` for `contradicts`/`does_not_support`, `needs_second_review` for `unclear`. Discordant
  AI-vs-anchor ratings are adjudicated to the anchor (`decider="human"`, the only allowed values
  are `human`/`panel`). The store must be `init`'d before ingest, and candidate sets need a
  `Provenance` stamp. Vocabulary maps: supports→directly_supports, contrasts→contradicts,
  unclear→unclear, not_relevant→does_not_support.
- **Ports.** 8790/8791/8792 were used by the first three themes' panels; pick a fresh one.
