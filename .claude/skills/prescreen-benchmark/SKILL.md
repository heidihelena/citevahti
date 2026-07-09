---
name: prescreen-benchmark
description: >-
  Benchmark local LLMs (Ollama models such as qwen3:14b, hermes3:8b) as CiteVahti citation
  prescreening agents on a chosen topic, and build the publication-style Atlas + a dedicated
  CiteVahti store from the run. Use this whenever the user wants to test how well small/local
  models rate claim-vs-source support, add a new topic/theme to the prescreen study, compare
  models against Claude or against a guideline anchor, compute agreement / Cohen's kappa,
  produce an evidence Atlas "to show on the website", grow the de-identified validation corpus,
  or investigate where a model's ratings go wrong (the "unclear" blind spot). Trigger on phrases
  like "test my local models as prescreeners", "benchmark qwen/hermes", "new theme/topic for the
  Atlas", "build a claim corpus for X", "how well does a laptop model prescreen citations", or
  "run the prescreen benchmark on <topic>".
---

# Prescreen benchmark — local LLMs as CiteVahti prescreening agents

This skill runs the experiment: take a topic, author a small corpus of *claim ↔ cited-source*
pairs each with an **independently-authored anchor label**, have local Ollama models (plus a
Claude column) prescreen every pair **blind**, then measure agreement, ingest the run into a
**dedicated** CiteVahti store, and render a self-contained Atlas.

CiteVahti is a local-first citation-integrity tool used in **live pilots with real
researchers**. A benchmark that overstates what a laptop model can do — or that quietly grades a
model against its own author — is exactly the kind of self-flattering evidence this product
exists to prevent. So the guardrails below are load-bearing, not decoration.

## Non-negotiable guardrails (read first)

1. **The anchor must be authored independently of every rater.** Agreement is *not* accuracy
   (house doctrine). If the same author writes the claims *and* the anchor *and* rates them, a
   100% score is self-consistency, not correctness. Best: the clinician/domain expert (or a
   cited guideline document) supplies the anchor labels; the models — Claude included — are then
   scored against that anchor through the identical blind prompt. Whenever the anchor was NOT
   independently authored, say so in the write-up.
2. **Frozen vocabulary.** Exactly four coarse labels: `supports`, `contrasts`, `unclear`,
   `not_relevant`. Never invent a new scale. (`ingest.py` maps these onto CiteVahti's canonical
   7-value support vocabulary.)
3. **Never touch the real pilot ledger.** Every run ingests into a *separate* root
   (`~/Documents/CiteVahti-<theme>`). The founder's ledger at `~/Documents/CiteVahti` is
   off-limits.
4. **Blind + human-first.** Models never see the anchor. In the store the anchor is the human
   rating; the model is the blind AI second opinion; divergences are adjudicated to the anchor.
5. **Trust language.** In any Atlas/report copy: check / assess, never *verify / prove /
   guarantee*. The Atlas already carries the "agreement ≠ accuracy" caveat — keep it.

See `references/method.md` for the full method, the confound analysis, and the findings so far.

## Prerequisites

- **Ollama running** with the models pulled (`ollama list`). qwen3:14b and hermes3:8b are the
  defaults; override with `LOCAL_MODELS="a,b"` and `THINKING_MODELS="a"` (thinking models need
  `think:false`).
- **Python** (stdlib only for `bench.py`/`atlas.py`/`prompt_v2.py`). `ingest.py` imports
  `citevahti`, so run it with `PYTHONPATH=<repo>/src` or an installed `citevahti`.
- Pick a **work directory** for outputs, e.g. `~/Documents/prescreen-runs/<theme>/`, and run the
  commands from there (all scripts read/write relative to the current directory).

## The pipeline

Let `SK=.claude/skills/prescreen-benchmark` and `REPO` = this repo root.

1. **Author the seed.** Copy `$SK/seeds/_TEMPLATE.json` to `<theme>.json`, set `theme`, and write
   ~40 pairs. Aim for a spread across all four labels, and deliberately include genuine
   `unclear` cases (on-topic snippet that does not resolve the claim) and a few `not_relevant`
   ones — that is where models fail and where the benchmark earns its keep. Existing seeds in
   `$SK/seeds/` are worked examples. **The anchor (`ref_status`) should come from the domain
   expert / guideline, not from the model that will be graded.**

2. **Run the benchmark** (queries the local models; caches so re-runs only hit changed pairs):
   ```
   python3 $SK/scripts/bench.py <theme>.json _<tag>
   ```
   → `results_<tag>.json`, `validation_records_<tag>.jsonl`, `ratings_cache_<tag>.json`.

3. **Render the Atlas:**
   ```
   python3 $SK/scripts/atlas.py results_<tag>.json atlas_<tag>.html
   ```
   For a nicer masthead on a brand-new theme, add a `META` entry in `atlas.py`; the fallback
   works without one. Publish the HTML as an artifact if the user wants a shareable page.

4. **Build a dedicated CiteVahti store and view it:**
   ```
   citevahti --root ~/Documents/CiteVahti-<theme> init
   PYTHONPATH=$REPO/src python3 $SK/scripts/ingest.py results_<tag>.json ~/Documents/CiteVahti-<theme> [panel_model]
   PYTHONPATH=$REPO/src citevahti-panel --root ~/Documents/CiteVahti-<theme> --port <free_port>
   ```
   `panel_model` (default `qwen3:14b`) is the local model whose blind rating becomes the store's
   AI second opinion; it must be one of the benchmarked models. Use a port other than any panel
   already running (8790, 8791, 8792 are in use by earlier runs).

5. **(Optional) Workflow / prompt test.** To check whether a model's errors are a *prompt* gap
   vs a capability ceiling, re-run with the "unclear"-scaffolding v2 prompt and diff against v1:
   ```
   python3 $SK/scripts/prompt_v2.py <theme>.json results_<tag>.json
   ```

## Reporting

Lead with the per-model agreement + Cohen's κ vs the anchor, then the divergences (which labels,
which direction). Always restate: the anchor is the reference, not ground truth about patients;
and note whether the anchor was independently authored. If it was not, that limitation goes at
the top, not the footnote.
