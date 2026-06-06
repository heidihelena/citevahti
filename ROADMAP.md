# Roadmap

CiteVahti is **free and local-first** for researchers, and it stays that way: the
local claim → evidence → blinded rating → decision → audited, undoable Zotero write
loop is Apache-2.0 and never requires an account.

## Direction

The near-term focus is reducing friction for ordinary academics and strengthening
the local review experience — see [`docs/RECAP.md`](docs/RECAP.md) for the current
working status.

Future work may include **team workflows, institutional deployments, and optional
de-identified aggregate reporting, governed by consent and privacy review.** Any
data that ever leaves a researcher's machine would be opt-in, de-identified, and
purgeable — see the warehouse governance in
[`docs/adr/0003-hosted-layer-and-open-core.md`](docs/adr/0003-hosted-layer-and-open-core.md).

## Principles that don't change

- **We never paywall a capability a lone researcher needs to verify their own
  manuscript.**
- The human is always the decider; the AI is a blinded, advisory second rater.
- No silent writes; everything is previewed, confirmed, undoable, and audited.
- Local-first, single-user, PubMed-only, no telemetry in the core.
