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
- **A low-rated model → switch to a better-covering one.** The read-only `model_advisor`
  tool returns this directly from *this project's own records*: a ranking by catch-rate, the
  recommended model, and — given a model id that rates low — a concrete better-evidenced
  alternative to switch to. The panel equivalent is *Settings → AI second opinion*. The
  nudge is about *coverage*, not raw agreement.
- **Rating is per-task and per-topic** — a model strong on oncology claims may be weak
  elsewhere; read the scoreboard for the topic at hand, not a single global number.

### Reading a model's standing (shipped, local — not Atlas)

Two read-only surfaces exist **today**, computed from this project's own rating records —
they change and adjudicate nothing:

- **`model_advisor`** — the operating tool. Call it to rank the identifiable models by
  complementary value, get the recommended second-rater, and pass a model id to ask "is this
  one still worth trusting?" It stays **silent on any model without enough resolved
  divergences to judge** (an evidence floor — a handful of catches is not a track record),
  and when a named model rates low it names a better-evidenced alternative. This is the
  executable form of "if a model rates low, suggest another".
- **`agreement_report`** → its `model_scoreboard` — the underlying per-model tally (catches
  / overruled / pending / catch-rate) if you want the raw counts behind the advice.

Both are **local** to this project. The *pooled* scoreboard across contributors is Atlas,
and it is roadmap (below) — don't present the local numbers as the pooled ones.

## Running one topic through several models

Independent models running the **same** topic are independent screening passes — where they
**diverge** is where the evidence is contested and human attention should go.

- **Shipped mechanism:** the `ai-screen` / `run_claim_tests` prompts (ADR-0007/0008 — the
  panel *prepares* the prompt; the assistant runs the model). Run the topic once per model,
  keep each model's id with its output, and compare the divergences by hand today. As those
  models' divergences get adjudicated, `model_advisor` accrues their local standings so the
  *next* pre-check starts from evidence, not a guess.
- **Roadmap (ADR-0009, needs Atlas):** the **pooled** model scoreboard and **divergence
  maps** — a layer over the Atlas evidence map that shows where models disagree, by
  claim/topic — aggregate object 2 across contributors. The *local* per-model scoreboard
  ships now (`model_advisor` / `agreement_report`); the cross-model *divergence map* does
  not. Until Atlas ships, do the divergence comparison manually and say so; don't imply a
  pooled scoreboard that isn't there yet (`citevahti-claims`).

### The 3-model guideline pre-check

A serious guideline group can run the same topic through **3 independent models before
starting**, then focus scarce human effort where the models diverge. This is **Layer-0
screening — leads, not verdicts** (ADR-0008 §Layer 0): it *prepares* the group's work. It
does **not** confer guideline grade, which still needs the human independent-assessor count
(~8+, ADR-0008). Multi-model agreement is a screening signal, never an evidence tier.

## Operate it

Picking or checking a second-rater model, end to end:

1. **Ask the advisor.** Call `model_advisor` (no argument) for the ranking + recommended
   model. If it recommends one, prefer that. If `ranked` is empty, the project has no model
   past the evidence floor yet — say so and pick on other grounds (identifiability,
   task fit), don't invent a standing.
2. **Check the model you're leaning toward.** Call `model_advisor` with its `model_id`. If it
   comes back with a `suggestion`, the model rates low on *this* project's divergences —
   relay the suggested alternative. If it's under the floor, report that honestly ("not
   enough resolved divergences to judge it yet") rather than treating silence as a pass.
3. **Set it** in the panel — *Settings → AI second opinion* — or record the chosen model id
   at `init` so its identity (and future rating) is captured.
4. **For a guideline pre-check**, run the topic through the chosen models (`ai-screen`
   prompts), keep each model id with its output, and take the divergences to the humans.

The advisor is descriptive — it reports standing; it never picks *for* the user or rates a
claim. The human decides which model to trust, and always decides the claim.

## Hard rules

- **NEVER let a model (single or multi) issue a verdict** — it surfaces evidence and
  disagreement; the human decides (ADR-0001).
- **NEVER rank a model by agreement with the human** — rank by complementary catches
  (ADR-0009). Agreement-ranking selects for redundant slices.
- **NEVER read a below-the-floor model as good OR bad** — `model_advisor` is silent on it on
  purpose; too few resolved divergences is *no track record*, not a verdict either way.
- **NEVER present multi-model agreement as an evidence tier** — it is Layer-0 screening;
  the ADR-0008 assessor count governs review/guideline grade.
- **NEVER imply the pooled Atlas scoreboard / divergence maps exist before they ship** — the
  *local* per-project scoreboard is real today; the pooled one and the divergence map are not.
- **NEVER rate or lean on an anonymous model** as if it had a track record.
