# Writing good claims — keep them atomic

CiteVahti tests **one claim against one source**. If a claim bundles several
assertions, the support judgment becomes ambiguous — a source might support one
part and not another, and "supported / not supported" no longer has a clean
answer.

## The rule

> **One claim test = one population · one intervention or exposure · one
> comparator (if any) · one outcome · one support question.**

If you can't answer *"does this source support this, yes or no?"* without saying
*"well, the first half yes, but…"*, the claim isn't atomic yet — split it.

## Example

A single manuscript sentence:

> "Low-dose CT screening reduces lung-cancer mortality and is cost-effective in
> high-risk European populations."

is really **three** claims, each needing its own source:

1. **LDCT reduces lung-cancer mortality.** (effect)
2. **The benefit holds in a high-risk population.** (population)
3. **It is cost-effective in European settings.** (economic, setting-specific)

One paper (e.g. a mortality RCT) may support #1 strongly, say nothing useful
about #3, and only partially address #2. Cited as one claim, it looks
"partially supported" — which hides that the cost-effectiveness assertion has **no
support at all**. Split, each part gets the source it actually needs.

## In practice

- When the assistant extracts claims, **prefer more, smaller claims** over fewer
  compound ones.
- When you add a claim by hand in the panel, **paste one assertion**, not a whole
  sentence, if the sentence makes several.
- A claim that overstates its source (broader population, stronger verb, extra
  outcome) usually isn't *rejected* — you **tighten the wording to match the
  evidence, then accept** (the revise-then-accept path).

Atomic claims make the report trustworthy: every green mark means *this exact
assertion* met *this exact source*.
