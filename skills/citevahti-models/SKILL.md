---
name: citevahti-models
description: Use when choosing or comparing the AI second-rater model in CiteVahti — picking a model, running the same topic through several models to see where they diverge, reading a model's rating/scoreboard standing, acting on a low-rated model, or setting up a multi-model pre-check before a guideline group starts. Follows ADR-0009 (models are cheese-slices: value is complementary catches, not agreement). Not for rating the lexical detector (citevahti-eval) or checking a manuscript (citevahti-dev).
---

# CiteVahti models — choosing and comparing the second rater

The AI second rater is **one slice of a defence-in-depth stack** (ADR-0009): the human,
the lexical detector, and one or more AI models, each with holes. Safety comes from layers
whose holes don't line up — so the model you want is the one that **catches what you miss**,
not the one that agrees with you most. This skill operates that dimension.

The human always decides. A model — one or several — **surfaces evidence and disagreement;
it never issues a verdict** (ADR-0001).

## Triggers

**Use when the researcher/maintainer asks to:** pick or switch the AI second-opinion model;
run a topic through several models and compare; read a model's rating or scoreboard
standing; respond to a "this model rates low" nudge; set up a multi-model pre-check for a
panel or guideline group.

**Do NOT use for:** evaluating the lexical detector (`citevahti-eval`), checking a
manuscript claim (`citevahti-dev`), or reference-list sweeps (`citevahti-screen`).

## How a model is rated (why "agrees with me" is the wrong test)

A model earns its place by **complementary catches**, not agreement (ADR-0009 §3b). The
signal is: the model's blinded rating **diverges** from the human, and on reveal the human
**adopts** the divergence — correcting the *statement* (rewording the claim) or the
*judgement* (changing the rating). That is a hole covered, and better science. A model that
mostly agrees is a redundant slice; its holes line up with yours.

Consequences you act on here:

- **Only identifiable models are rated** — you can't build a track record for an anonymous
  model. Prefer a model whose id + version is recorded (the AI-provenance summary,
  METHODS.md).
- **A low-rated model → switch to a better-covering one.** In the panel: *Settings → AI
  second opinion*. The nudge is about *coverage*, not raw agreement.
- **Rating is per-task and per-topic** — a model strong on oncology claims may be weak
  elsewhere; read the scoreboard for the topic at hand, not a single global number.

## Running one topic through several models

Independent models running the **same** topic are independent screening passes — where they
**diverge** is where the evidence is contested and human attention should go.

- **Shipped mechanism:** the `ai-screen` / `run_claim_tests` prompts (ADR-0007/0008 — the
  panel *prepares* the prompt; the assistant runs the model). Run the topic once per model,
  keep each model's id with its output, and compare the divergences by hand today.
- **Roadmap (ADR-0009, needs Atlas):** the **model scoreboard** and **divergence maps** — a
  layer over the Atlas evidence map that shows where models disagree, by claim/topic —
  aggregate this across contributors. Until Atlas ships, do the comparison manually and say
  so; don't imply a scoreboard that isn't there yet (`citevahti-claims`).

### The 3-model guideline pre-check

A serious guideline group can run the same topic through **3 independent models before
starting**, then focus scarce human effort where the models diverge. This is **Layer-0
screening — leads, not verdicts** (ADR-0008 §Layer 0): it *prepares* the group's work. It
does **not** confer guideline grade, which still needs the human independent-assessor count
(~8+, ADR-0008). Multi-model agreement is a screening signal, never an evidence tier.

## Hard rules

- **NEVER let a model (single or multi) issue a verdict** — it surfaces evidence and
  disagreement; the human decides (ADR-0001).
- **NEVER rank a model by agreement with the human** — rank by complementary catches
  (ADR-0009). Agreement-ranking selects for redundant slices.
- **NEVER present multi-model agreement as an evidence tier** — it is Layer-0 screening;
  the ADR-0008 assessor count governs review/guideline grade.
- **NEVER imply the Atlas scoreboard / divergence maps exist before they ship** — say what
  is manual today.
- **NEVER rate or lean on an anonymous model** as if it had a track record.
